import sqlite3
from unittest.mock import patch

import pytest

from app import create_app
from app.database.migrations import upgrade
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.repositories.quote_management_repository import (
    QuoteManagementRepository,
)
from app.workspace.services.project_workspace_service import ProjectWorkspaceService
from app.workspace.services.quote_management_service import QuoteManagementService


@pytest.fixture
def quote_database(tmp_path, monkeypatch):
    path = tmp_path / "quote-opportunity.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO ws_customers(id,name,erp_customer_id) "
            "VALUES (1,'Cliente Uno','9001')"
        )
    return path


def _direct_quote():
    return QuoteManagementService.create_direct({
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


def test_quote_without_opportunity_offers_prefilled_creation(quote_database):
    quote_id = _direct_quote()
    application = create_app({
        "TESTING": True,
        "TEST_AUTH_BYPASS": True,
    }, run_migrations=False)
    client = application.test_client()

    quote_response = client.get(f"/quotes/{quote_id}")
    assert quote_response.status_code == 200
    assert b"Crear oportunidad desde esta cotizaci" in quote_response.data

    form_response = client.get(
        f"/workspace/projects/new?source_quote_id={quote_id}"
    )
    assert form_response.status_code == 200
    html = form_response.get_data(as_text=True)
    assert "Cotización RL-" in html
    assert "LMH 20 UU" in html
    assert b'value="THK"' in form_response.data
    assert b"checked" in form_response.data


def test_creating_opportunity_links_existing_quote_without_duplicate(
    quote_database,
):
    quote_id = _direct_quote()
    with (
        patch(
            "app.workspace.services.project_workspace_service."
            "CustomerLookupRepository.get_customer_site",
            return_value={"customer_id": "9001", "customer_name": "Cliente Uno"},
        ),
        patch(
            "app.workspace.services.project_workspace_service."
            "ActivityRepository.create_activity",
        ),
        patch.object(
            ProjectWorkspaceService,
            "get_workspace",
            side_effect=lambda project_id: {
                "project": ProjectRepository.get_project(project_id)
            },
        ),
    ):
        workspace = ProjectWorkspaceService.create_project_mvp(
            erp_customer_id="9001",
            customer_site_id="SITE-1",
            project_name="Cotización convertida",
            objective="Cerrar la orden del cliente",
            sales_rep="Maria Sierra",
            status="negotiation",
            brands=["THK"],
            source_quote_id=quote_id,
        )

    quote = QuoteManagementRepository.get(quote_id)
    assert quote["project_id"] == workspace["project"]["id"]
    assert quote["opportunity_name"] == "Cotización convertida"
    with sqlite3.connect(quote_database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM ws_project_quotes"
        ).fetchone()[0] == 1
