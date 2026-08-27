import sqlite3

import pytest

from app.database.migrations import upgrade
from app.workspace.services.rfq_service import RFQService


@pytest.fixture
def rfq_database(tmp_path, monkeypatch):
    path = tmp_path / "rfq.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO ws_customers (id, name) VALUES (1, 'Cliente')"
        )
    return path


def _values():
    return {
        "customer_id": 1,
        "received_at": "2026-07-23", "description": "Rodamientos especiales",
        "prequotation_number": "PC-2026-0001",
        "items": [{
            "reference": "22220", "brand": "SKF", "quantity": "2",
            "notes": "",
        }],
    }


def test_rfq_is_created_without_opportunity(rfq_database):
    rfq_id = RFQService.create(_values())
    page = RFQService.detail(rfq_id)

    assert page["rfq"]["status"] == "received"
    assert page["rfq"]["opportunity_id"] is None
    assert page["rfq"]["workflow_status"] == "draft"
    assert page["items"][0]["reference"] == "22220"


def test_new_rfq_does_not_require_legacy_commercial_fields(rfq_database):
    values = _values()
    values.update({
        "next_action": "", "estimated_value": "", "currency_code": "",
    })
    assert RFQService.create(values)


def test_cancelled_rfq_requires_reason(rfq_database):
    rfq_id = RFQService.create(_values())
    with pytest.raises(ValueError, match="requiere un motivo"):
        RFQService.conclude(rfq_id, outcome="cancelled")


def test_explicit_conversion_creates_and_links_opportunity(rfq_database):
    rfq_id = RFQService.create(_values())
    RFQService.conclude(rfq_id, outcome="opportunity")
    page = RFQService.detail(rfq_id)

    assert page["rfq"]["status"] == "opportunity"
    assert page["rfq"]["opportunity_id"] is not None
    assert page["conclusion"]["opportunity_id"] == page["rfq"]["opportunity_id"]
