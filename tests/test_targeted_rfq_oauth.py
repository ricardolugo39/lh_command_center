import os
import sqlite3
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest

from app import create_app
from app.auth.oauth import GoogleOAuthProvider
from app.database.migrations import upgrade
from app.workspace.repositories.customer_lookup_repository import (
    CustomerLookupRepository,
)
from app.workspace.repositories.rfq_email_repository import RFQEmailRepository
from app.workspace.services.erp_import_service import (
    ERPImportService, ERPImportValidationError,
)
from app.workspace.services.rfq_email_service import RFQEmailService
from app.workspace.services.rfq_service import RFQService
from app.workspace.services.rfq_vendor_request_service import (
    RFQVendorRequestService,
)
from app.workspace.repositories.rfq_vendor_request_repository import (
    RFQVendorRequestRepository,
)


REQUIRED_CUSTOMER = {
    "NIT": "9001", "RAZONSOCIAL": "Cliente", "CIUDAD": "Cali",
    "VENDEDOR": "Asesor", "CLIENTE_CREDITO": "S",
    "CUPOCREDITOCC": 100, "PLAZOPAGOCC": 30, "IDCIIU": "1",
}


@pytest.fixture
def targeted_database(tmp_path, monkeypatch):
    path = tmp_path / "targeted.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """INSERT INTO ws_customers(id,name,erp_customer_id)
            VALUES (1,'IMECOL S.A.S.','900123456')"""
        )
        connection.execute(
            """CREATE TABLE raw_customers (
                ID TEXT PRIMARY KEY, nit TEXT, razonsocial TEXT
            )"""
        )
        connection.execute(
            """INSERT INTO raw_customers(ID,nit,razonsocial)
            VALUES ('12345','900123456','IMECOL S.A.S.')"""
        )
    return path


def _rfq_values(number="PC-2026-0001"):
    return {
        "customer_id": 1, "prequotation_number": number,
        "received_at": "2026-07-23", "description": "Solicitud",
        "items": [
            {"reference": "A<script>", "brand": "SKF", "quantity": "2"},
            {"reference": "B", "brand": "THK", "quantity": "1", "notes": "Urgente"},
        ],
    }


@pytest.mark.parametrize("header", ["NIT", "Nit", "nit", "  NIT  "])
def test_erp_customer_nit_header_is_normalized(header):
    values = dict(REQUIRED_CUSTOMER)
    values.pop("NIT")
    values["DIRECCION1"] = "Calle 1"
    frame = pd.DataFrame([{header: "123", **values}])
    normalized, _, mapping = ERPImportService._validate("customers", frame)
    assert normalized.iloc[0]["nit"] == "123"
    assert (header, "nit") in mapping


def test_erp_customer_nit_ambiguity_and_missing_errors():
    values = dict(REQUIRED_CUSTOMER)
    values.pop("NIT")
    values["DIRECCION1"] = "Calle 1"
    ambiguous = pd.DataFrame([{
        "NIT": "1", "nit": "2", **values,
    }])
    with pytest.raises(ERPImportValidationError, match="ambigu"):
        ERPImportService._validate("customers", ambiguous)
    missing = pd.DataFrame([values])
    with pytest.raises(
        ERPImportValidationError,
        match="Faltan columnas obligatorias: nit",
    ):
        ERPImportService._validate("customers", missing)


def test_customer_autocomplete_searches_name_nit_and_erp_id(targeted_database):
    for query in ("IMECOL", "900123456", "12345"):
        results = CustomerLookupRepository.search_workspace_customers(query, 1)
        assert results[0]["workspace_customer_id"] == 1
    assert len(CustomerLookupRepository.search_workspace_customers("I", 1)) <= 1


def test_rfq_can_create_a_customer_not_present_in_erp(targeted_database):
    values = _rfq_values()
    values["customer_id"] = ""
    values["new_customer_name"] = "Cliente Nuevo de Prueba"
    rfq_id = RFQService.create(values)
    assert RFQService.detail(rfq_id)["rfq"]["customer_name"] == (
        "Cliente Nuevo de Prueba"
    )


def test_draft_rfq_can_be_deleted_but_sent_rfq_cannot(targeted_database):
    draft_id = RFQService.create(_rfq_values("DELETE-ME"))
    assert RFQService.delete_draft(draft_id) == []
    with pytest.raises(ValueError, match="no existe"):
        RFQService.require(draft_id)


def test_rfq_rules_and_normalized_unique_number(targeted_database):
    first = RFQService.create(_rfq_values())
    assert RFQService.detail(first)["rfq"]["opportunity_id"] is None
    assert len(RFQService.detail(first)["items"]) == 2
    with pytest.raises(ValueError, match="ya está registrado"):
        RFQService.create(_rfq_values("  pc-2026-0001 "))
    values = _rfq_values("PC-2")
    values["items"] = []
    with pytest.raises(ValueError, match="al menos una"):
        RFQService.create(values)
    with pytest.raises(ValueError, match="requiere un motivo"):
        RFQService.conclude(first, outcome="cancelled")
    automatic = _rfq_values("")
    created = RFQService.create(automatic)
    assert RFQService.detail(created)["rfq"]["rfq_number"].startswith("RFQ-")


class FakeGmail:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = None

    def send(self, **values):
        if self.fail:
            raise RuntimeError("offline")
        self.sent = values
        return {"message_id": "m-1", "thread_id": "t-1"}

    def thread(self, thread_id):
        return [{
            "id": "m-2", "direction": "incoming", "sender": "vendor@example.com",
            "recipients": [], "cc": [], "subject": "Re: PC", "body_text":
            "<script>alert(1)</script>", "date": "2026-07-24T10:00:00",
        }]


def test_gmail_send_sync_and_failure_are_safe(targeted_database):
    rfq_id = RFQService.create(_rfq_values())
    gmail = FakeGmail()
    application = create_app(
        {"TESTING": True, "TEST_AUTH_BYPASS": True},
        run_migrations=False, gmail_provider=gmail,
    )
    with application.app_context():
        RFQEmailService.send(rfq_id)
        assert "&lt;script&gt;" in gmail.sent["body_html"]
        RFQEmailService.sync(rfq_id)
    assert RFQService.detail(rfq_id)["rfq"]["workflow_status"] == "sent"
    assert len(RFQEmailRepository.list_messages(rfq_id)) == 2
    assert "<script>" not in RFQEmailRepository.list_messages(rfq_id)[1][
        "body_html_sanitized"
    ]

    second = RFQService.create(_rfq_values("PC-FAIL"))
    application.extensions["gmail_provider"] = FakeGmail(fail=True)
    with application.app_context(), pytest.raises(ValueError, match="se conservó"):
        RFQEmailService.send(second)
    assert RFQService.detail(second)["rfq"]["workflow_status"] == "draft"


def test_vendor_rfq_send_and_sync_tracks_real_reply(targeted_database):
    values = _rfq_values("RL-2001")
    values["items"] = [
        {"reference": "HSR25", "brand": "THK", "quantity": "2"},
        {"reference": "SBN4555", "brand": "Thomson", "quantity": "1"},
    ]
    values.pop("prequotation_number")
    rfq_id = RFQService.create(values)
    rfq = RFQService.detail(rfq_id)["rfq"]
    assert rfq["rfq_number"].startswith("RFQ-")
    assert rfq["prequotation_number"] is None
    assert rfq["owner_email"] == "ricardo.lugo@lugohermanos.com"

    class VendorGmail:
        def __init__(self):
            self.sent = []

        def send(self, **message):
            self.sent.append(message)
            index = len(self.sent)
            return {"message_id": f"m-{index}", "thread_id": f"t-{index}"}

        def thread(self, thread_id):
            return [{
                "id": f"reply-{thread_id}", "direction": "incoming",
                "sender": "vendor@example.com", "recipients": [], "cc": [],
                "subject": "Re: RFQ", "body_text": "<b>Quote attached</b>",
                "date": "2026-07-24T10:00:00",
            }]

    gmail = VendorGmail()
    application = create_app(
        {"TESTING": True, "TEST_AUTH_BYPASS": True},
        run_migrations=False, gmail_provider=gmail,
    )
    with application.app_context():
        assert RFQVendorRequestService.send_test(rfq_id) == 2
        assert gmail.sent[0]["recipients"] == ["ricardo.lugo@lugohermanos.com"]
        assert gmail.sent[0]["subject"].startswith("[PRUEBA]")
        assert RFQVendorRequestRepository.list_for_rfq(rfq_id) == []
        assert RFQVendorRequestService.send(rfq_id, 1) == 2
        assert len(gmail.sent) == 4
        assert rfq["rfq_number"] in gmail.sent[2]["subject"]
        assert rfq["rfq_number"] in gmail.sent[2]["body_text"]
        assert gmail.sent[2]["subject"] == "RFQ-000001 - THK"
        assert "Hello," in gmail.sent[2]["body_text"]
        assert "RFQ-000001" in gmail.sent[2]["body_text"]
        assert "HSR25" in gmail.sent[2]["body_text"]
        assert "SBN4555" in gmail.sent[3]["body_text"]
        assert RFQVendorRequestRepository.pending_rfq_ids() == [rfq_id]
        with pytest.raises(ValueError, match="ya fue enviada"):
            RFQVendorRequestService.send(rfq_id, 1)
        assert RFQVendorRequestService.sync(rfq_id, 1) == 2

    requests = RFQVendorRequestRepository.list_for_rfq(rfq_id)
    assert all(request["has_response"] for request in requests)
    assert all(request["status"] == "responded" for request in requests)
    assert len(RFQVendorRequestRepository.list_messages(rfq_id)) == 4
    assert RFQService.detail(rfq_id)["rfq"]["workflow_status"] == "answered"
    assert "<b>" not in RFQVendorRequestRepository.list_messages(rfq_id)[-1][
        "body_html_sanitized"
    ]


def test_vendor_reply_in_new_thread_and_pdf_are_captured(targeted_database):
    values = _rfq_values("NEW-THREAD")
    values["items"] = [
        {"reference": "SBN4555", "brand": "Thomson", "quantity": "1"},
    ]
    rfq_id = RFQService.create(values)

    class NewThreadGmail:
        queries = []

        def send(self, **message):
            return {"message_id": "sent-1", "thread_id": "original-thread"}

        def thread(self, thread_id):
            return []

        def search(self, query):
            self.queries.append(query)
            assert "RFQ-000001" in query
            return [{
                "id": "new-thread-reply", "direction": "incoming",
                "sender": "vendor@example.com", "recipients": [], "cc": [],
                "subject": "Quotation RFQ-000001", "body_text": "Attached",
                "date": "2026-07-24T10:00:00", "attachments": [{
                    "id": "pdf-1", "filename": "quotation.pdf",
                    "mime_type": "application/pdf", "data": b"%PDF-test",
                }],
            }]

    application = create_app(
        {"TESTING": True, "TEST_AUTH_BYPASS": True},
        run_migrations=False, gmail_provider=NewThreadGmail(),
    )
    with sqlite3.connect(targeted_database) as connection:
        connection.execute(
            """UPDATE quote_vendor_configs SET vendor_email='vendor@example.com'
            WHERE brand='Thomson' COLLATE NOCASE"""
        )
    with application.app_context():
        RFQVendorRequestService.send(rfq_id, 1)
        assert RFQVendorRequestService.sync(rfq_id, 1) == 1
    page = RFQService.detail(rfq_id)
    assert page["vendor_requests"][0]["has_response"]
    assert page["vendor_attachments"][0]["original_filename"] == "quotation.pdf"
    assert any("vendor@example.com" in query for query in NewThreadGmail.queries)
    assert any('subject:"RFQ-000001" "Thomson"' == query for query in NewThreadGmail.queries)


class FakeOAuth:
    def __init__(self, identity):
        self.identity = identity
        self.received_code_verifier = None

    def configured(self):
        return True

    def authorization_url(self):
        return "https://accounts.example/auth", "state-1", "verifier-1"

    def fetch_identity(self, response, *, code_verifier):
        self.received_code_verifier = code_verifier
        return self.identity


def test_oauth_login_identity_logout_and_protection(targeted_database):
    provider = FakeOAuth({
        "subject": "google-ricardo", "email": "ricardo.lugo@lugohermanos.com",
        "name": "Ricardo Lugo", "email_verified": True,
    })
    app = create_app(
        {
            "TESTING": True, "SECRET_KEY": "test-secret-key-with-more-than-32-characters",
            "TEST_AUTH_BYPASS": False,
            "GOOGLE_OAUTH_CLIENT_ID": "client.apps.googleusercontent.com",
            "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
        },
        run_migrations=False, oauth_provider=provider,
    )
    client = app.test_client()
    assert client.get("/rfqs/").status_code == 302
    response = client.get("/auth/google")
    assert response.location == "https://accounts.example/auth"
    response = client.get("/auth/callback?state=state-1")
    assert response.status_code == 302
    assert provider.received_code_verifier == "verifier-1"
    assert client.get("/rfqs/").status_code == 200
    with sqlite3.connect(targeted_database) as connection:
        assert connection.execute(
            """SELECT google_subject FROM ws_users
            WHERE email_normalized='ricardo.lugo@lugohermanos.com'"""
        ).fetchone()[0] == "google-ricardo"
    assert client.post("/auth/logout").status_code == 302
    assert client.get("/rfqs/").status_code == 302


def test_insecure_oauth_transport_is_scoped_to_development_loopback(
    targeted_database, monkeypatch,
):
    monkeypatch.delenv("OAUTHLIB_INSECURE_TRANSPORT", raising=False)
    development = create_app(
        {
            "TESTING": True,
            "FLASK_ENV": "development",
            "GOOGLE_OAUTH_REDIRECT_URI":
                "http://127.0.0.1:5000/auth/callback",
        },
        run_migrations=False,
    )
    with development.app_context():
        with GoogleOAuthProvider._local_http_transport(
            "http://127.0.0.1:5000/auth/callback?code=test"
        ):
            assert os.environ["OAUTHLIB_INSECURE_TRANSPORT"] == "1"
        assert "OAUTHLIB_INSECURE_TRANSPORT" not in os.environ

    production = create_app(
        {
            "TESTING": True,
            "FLASK_ENV": "production",
            "GOOGLE_OAUTH_REDIRECT_URI":
                "http://127.0.0.1:5000/auth/callback",
        },
        run_migrations=False,
    )
    with production.app_context():
        with GoogleOAuthProvider._local_http_transport(
            "http://127.0.0.1:5000/auth/callback?code=test"
        ):
            assert "OAUTHLIB_INSECURE_TRANSPORT" not in os.environ


def test_google_login_scopes_do_not_merge_gmail_grants(targeted_database):
    application = create_app(
        {"TESTING": True, "FLASK_ENV": "development"},
        run_migrations=False,
    )
    with application.app_context():
        authorization_url, _, verifier = (
            GoogleOAuthProvider().authorization_url()
        )
    query = parse_qs(urlsplit(authorization_url).query)
    assert "include_granted_scopes" not in query
    assert query["access_type"] == ["online"]
    assert set(query["scope"][0].split()) == {
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    }
    assert verifier


def test_oauth_scope_warning_is_handled_without_debugger(targeted_database):
    class ScopeWarningOAuth(FakeOAuth):
        def fetch_identity(self, response, *, code_verifier):
            raise Warning("Scope has changed")

    application = create_app(
        {"TESTING": True, "SECRET_KEY": "test-secret"},
        run_migrations=False,
        oauth_provider=ScopeWarningOAuth({}),
    )
    client = application.test_client()
    client.get("/auth/google")
    response = client.get("/auth/callback?state=state-1")
    assert response.status_code == 302
    assert "error=oauth_failed" in response.location


def test_oauth_rejects_unapproved_domain_and_inactive_user(targeted_database):
    identities = (
        {
            "subject": "outside", "email": "person@example.com",
            "name": "Outside", "email_verified": True,
        },
        {
            "subject": "inactive", "email": "jeanp.florez@lugohermanos.com",
            "name": "Jean", "email_verified": True,
        },
    )
    with sqlite3.connect(targeted_database) as connection:
        connection.execute(
            """UPDATE ws_users SET is_active=0
            WHERE email_normalized='jeanp.florez@lugohermanos.com'"""
        )
    for identity in identities:
        app = create_app(
            {"TESTING": True, "SECRET_KEY": "test"},
            run_migrations=False, oauth_provider=FakeOAuth(identity),
        )
        client = app.test_client()
        client.get("/auth/google")
        response = client.get("/auth/callback?state=state-1")
        assert "error=oauth_failed" in response.location


def test_auth_bypass_is_testing_only_and_read_only_cannot_import(
    targeted_database,
):
    app = create_app(
        {"SECRET_KEY": "test", "TEST_AUTH_BYPASS": True},
        run_migrations=False,
    )
    assert app.test_client().get("/rfqs/").status_code == 302
    with sqlite3.connect(targeted_database) as connection:
        connection.execute(
            """UPDATE ws_users SET role='read_only'
            WHERE email_normalized='ricardo.lugo@lugohermanos.com'"""
        )
    app = create_app(
        {
            "TESTING": True, "TEST_AUTH_BYPASS": True,
            "TEST_AUTH_USER_ID": 2,
        },
        run_migrations=False,
    )
    assert app.test_client().get("/imports/").status_code == 403


def test_oauth_status_explains_missing_values_and_sources(targeted_database):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "from-flask-config-with-at-least-32-characters",
            "GOOGLE_OAUTH_CLIENT_ID": "client.apps.googleusercontent.com",
        },
        run_migrations=False,
    )
    response = app.test_client().get("/auth/status")
    assert response.status_code == 200
    assert b"GOOGLE_OAUTH_CLIENT_SECRET" in response.data
    assert b"Faltante" in response.data
    assert b"Flask config" in response.data
    assert b"/auth/callback" in response.data


def test_development_admin_login_exists_only_in_development(
    targeted_database,
):
    development = create_app(
        {"TESTING": True, "FLASK_ENV": "development"},
        run_migrations=False,
    )
    client = development.test_client()
    login = client.get("/auth/login")
    assert b"Development Only" in login.data
    assert client.post("/auth/development-login").status_code == 302
    assert client.get("/rfqs/").status_code == 200

    production = create_app(
        {"TESTING": True, "FLASK_ENV": "production"},
        run_migrations=False,
    )
    assert b"Development Only" not in production.test_client().get(
        "/auth/login"
    ).data
    assert production.test_client().post(
        "/auth/development-login"
    ).status_code == 404
