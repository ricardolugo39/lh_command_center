import sqlite3

import pytest

from app.database.migrations import upgrade
from app.workspace.repositories.rfq_repository import RFQRepository
from app.workspace.services.rfq_service import RFQService


@pytest.fixture
def rfq_database(tmp_path, monkeypatch):
    path = tmp_path / "rfq-archive.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO ws_customers(id,name,erp_customer_id) "
            "VALUES (1,'Cliente Uno','9001')"
        )
    return path


def test_cancelled_rfq_is_hidden_from_active_lists_and_kept_in_archive(
    rfq_database,
):
    rfq_id = RFQService.create({
        "customer_id": 1,
        "prequotation_number": "PC-ARCHIVED",
        "received_at": "2026-10-05",
        "description": "Solicitud que ya no se necesita",
        "items": [{
            "reference": "SR20W",
            "brand": "THK",
            "quantity": "1",
            "notes": "",
        }],
    })
    RFQService.conclude(
        rfq_id,
        outcome="cancelled",
        reason="Ya no se necesita",
    )

    assert RFQRepository.list_all() == []
    assert RFQRepository.list_all(quote_scope="all") == []
    assert [row["id"] for row in RFQRepository.list_all(
        quote_scope="archived"
    )] == [rfq_id]
