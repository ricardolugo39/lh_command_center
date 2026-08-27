import pytest
from flask import Flask

from app.routes import register_blueprints


@pytest.fixture
def client():
    application = Flask(__name__, template_folder="../app/templates",
                        static_folder="../app/static")
    register_blueprints(application)
    return application.test_client()


def _overview_page(*, has_agreement: bool):
    agreement = {
        "name": "Acuerdo 2026" if has_agreement else "Acuerdo estratégico",
        "status_label": "Activo" if has_agreement else "Sin información",
        "period": "01 ene 2026 — 31 dic 2026" if has_agreement else "Periodo por definir",
        "is_temporary": not has_agreement,
    }
    if has_agreement:
        agreement.update(readiness_label="12 productos negociados", supplier="SKF",
                         days_remaining=100)
    return {
        "account": {"id": 7, "name": "Cliente Uno", "sales_rep": "Ana"},
        "agreement": agreement,
        "executive_summary": [], "kpis": [],
        "revenue_comparison": {"points": [], "has_current": False,
                               "has_previous": False},
        "engagement": {"tone": "neutral", "status": "Sin registro",
                       "last_visit": "Sin registro", "last_activity": "Sin registro",
                       "days_label": "Sin registro", "follow_up": "Programar contacto"},
        "activity_metrics": [], "product_families": [],
        "recent_activities": [], "opportunities": [],
    }


def test_customer_list_links_to_canonical_account(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.workspace.CustomerPortfolioService.get_dashboard",
        lambda **kwargs: {
            "customers": [{"workspace_id": 7, "erp_customer_id": "1",
                "customer_name": "Cliente Uno", "city": "Bogotá",
                "status": {"label": "Buena", "tone": "neutral"},
                "display_revenue": "COP 0", "growth_label": "Sin base LY",
                "growth_tone": "neutral", "agreement_label": "Sin acuerdo",
                "additional_agreements": 0,
                "coverage": {"percentage": None}, "last_activity_label": "Sin actividad",
                "last_activity_age": "Sin actividad registrada", "open_opportunities": 0,
                "next_action": {"label": "Programar visita", "detail": "Sin actividad", "tone": "warning"}}],
            "kpis": [], "filters": [],
            "dimensions": {"offices": ["Cali", "Bogotá"], "advisors": ["Ana"]},
            "query": {"q": "", "filter": "", "office": "", "advisor": "",
                      "sort": "state", "direction": "desc"},
            "pagination": {"total": 1, "page": 1, "pages": 1,
                           "has_previous": False, "has_next": False},
        },
    )
    response = client.get("/workspace/customers")
    assert b'/workspace/strategic-accounts/7' in response.data
    assert b'/workspace/customers/7"' not in response.data
    assert response.data.count(b'<tr class="cp-row"') == 1
    assert response.data.count(b"<td") == 9
    assert b"ERP 1" in response.data
    assert b"ERP / NIT" not in response.data


def test_legacy_customer_url_redirects_to_workspace(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.workspace.CustomerRepository.get_customer",
        lambda customer_id: {"id": customer_id},
    )
    response = client.get("/workspace/customers/7")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/workspace/strategic-accounts/7"
    )


@pytest.mark.parametrize(
    ("has_agreement", "action"),
    [(False, "Cargar acuerdo"), (True, "Ver acuerdo")],
)
def test_overview_links_to_real_agreement_page(
    client, monkeypatch, has_agreement, action
):
    monkeypatch.setattr(
        "app.routes.workspace.StrategicAccountService.get_overview",
        lambda customer_id: _overview_page(has_agreement=has_agreement),
    )
    response = client.get("/workspace/strategic-accounts/7")
    assert response.status_code == 200
    assert action.encode() in response.data
    assert b"/workspace/strategic-accounts/7/agreement" in response.data


def test_empty_agreement_links_to_upload(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.workspace.AgreementService.get_customer_page",
        lambda *args, **kwargs: {
            "customer": {"id": 7, "name": "Cliente Uno"},
            "agreement": None, "items": [], "document": None,
        },
    )
    response = client.get("/workspace/strategic-accounts/7/agreement")
    assert response.status_code == 200
    assert b"Cargar acuerdo" in response.data
    assert b"/workspace/strategic-accounts/7/agreement/upload" in response.data
