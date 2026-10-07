import sqlite3

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
