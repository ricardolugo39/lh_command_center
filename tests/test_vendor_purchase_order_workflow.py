import sqlite3
from io import BytesIO

import pytest

from app import create_app
from app.database.migrations import upgrade
from app.workspace.services.quote_management_service import QuoteManagementService
from app.workspace.services.rfq_service import RFQService


@pytest.fixture
def quote_database(tmp_path, monkeypatch):
    path = tmp_path / "vendor-po.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO ws_customers(id,name,erp_customer_id) "
            "VALUES (1,'Cliente Uno','9001')"
        )
    return path


def test_vendor_po_action_remains_available_after_quote_is_won(quote_database):
    rfq_id = RFQService.create({
        "customer_id": 1,
        "prequotation_number": "PC-PO-1",
        "received_at": "2026-10-07",
        "description": "Solicitud con orden confirmada",
        "items": [{
            "reference": "SR20W",
            "brand": "THK",
            "quantity": "2",
        }],
    })
    quote_id = QuoteManagementService.create_from_rfq(rfq_id, 1)
    with sqlite3.connect(quote_database) as connection:
        connection.execute(
            "UPDATE ws_project_quotes SET quote_status='won' WHERE id=?",
            (quote_id,),
        )

    page = QuoteManagementService.workspace(quote_id)
    assert page["purchase_order_available"] is True

    application = create_app({
        "TESTING": True,
        "TEST_AUTH_BYPASS": True,
    }, run_migrations=False)
    response = application.test_client().get(f"/quotes/{quote_id}")
    assert response.status_code == 200
    assert b"Orden de compra al proveedor" in response.data
    assert b"Crear borrador de PO en Outlook" in response.data


def test_direct_quote_creates_outlook_draft_with_uploaded_vendor_pdf(
    quote_database,
):
    quote_id = QuoteManagementService.create_direct({
        "customer_id": 1,
        "sales_rep_name": "Maria Sierra",
        "sales_rep_email": "ventasonline@lugohermanos.com",
        "items": [{
            "reference": "LMH 20 UU",
            "brand": "THK",
            "quantity": "23",
            "fob_unit_usd": "299",
            "unit_weight_kg": "0.5",
            "lead_time": "4 weeks",
            "product_type": "BRG",
        }],
    }, 1)
    with sqlite3.connect(quote_database) as connection:
        connection.execute(
            "UPDATE ws_project_quotes SET quote_status='sent_sales_rep' WHERE id=?",
            (quote_id,),
        )

    class MailProvider:
        payload = None

        def create_message_draft(self, **payload):
            self.payload = payload
            return {
                "draft_id": "draft-1",
                "message_id": "message-1",
                "thread_id": "thread-1",
            }

    provider = MailProvider()
    application = create_app({
        "TESTING": True,
        "TEST_AUTH_BYPASS": True,
        "EMAIL_PROVIDER": "microsoft",
    }, run_migrations=False)
    application.extensions["email_provider"] = provider
    response = application.test_client().post(
        f"/quotes/{quote_id}/vendor-po-draft",
        data={
            "vendor_name": "THK",
            "vendor_email": "ignored@example.com",
            "vendor_quote_pdf": (BytesIO(b"%PDF-1.4 vendor quote"), "quote.pdf"),
            "purchase_order_pdf": (BytesIO(b"%PDF-1.4 purchase order"), "po.pdf"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert provider.payload["recipients"] == ["vendas@thk.com.br"]
    assert [item["filename"] for item in provider.payload["attachments"]] == [
        "quote.pdf", "po.pdf",
    ]
    with sqlite3.connect(quote_database) as connection:
        draft = connection.execute(
            "SELECT recipient_email,status FROM direct_vendor_purchase_order_drafts "
            "WHERE quote_id=?",
            (quote_id,),
        ).fetchone()
    assert draft == ("vendas@thk.com.br", "draft")
