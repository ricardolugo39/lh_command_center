import sqlite3
from decimal import Decimal

import pytest

from app.database.migrations import upgrade
from app.workspace.repositories.quote_management_repository import QuoteManagementRepository
from app.workspace.services.quote_management_service import QuoteManagementService
from app.workspace.services.rfq_service import RFQService


@pytest.fixture
def quote_database(tmp_path, monkeypatch):
    path = tmp_path / "quotes.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO ws_customers(id,name,erp_customer_id) VALUES (1,'Cliente Uno','9001')"
        )
    return path


def _rfq():
    return RFQService.create({
        "customer_id": 1, "prequotation_number": "PC-42",
        "received_at": "2026-08-03", "description": "Solicitud heredada",
        "items": [{
            "reference": "SR20W", "brand": "THK", "quantity": "2",
            "notes": "Con plano",
        }],
    })


def test_rfq_conversion_preserves_request_and_lines(quote_database):
    rfq_id = _rfq()
    quote_id = QuoteManagementService.create_from_rfq(rfq_id, 1)
    page = QuoteManagementService.workspace(quote_id)
    assert page["quote"]["originating_rfq_id"] == rfq_id
    assert page["quote"]["rfq_number_snapshot"] == "PC-42"
    assert page["quote"]["request_comments_snapshot"] == "Solicitud heredada"
    assert page["quote"]["currency_code"] == "USD"
    assert page["lines"][0]["source_rfq_item_id"]
    assert page["lines"][0]["part_number"] == "SR20W"
    assert page["lines"][0]["quantity"] == 2


def test_dhl_customs_bank_and_allocations_are_decimal_safe(quote_database):
    quote_id = QuoteManagementService.create_from_rfq(_rfq(), 1)
    line = QuoteManagementRepository.lines(quote_id)[0]
    QuoteManagementService.save_workspace(
        quote_id,
        {
            "estimated_trm": "4000", "origin_country_code": "BR",
            "origin_service_area_code": "default",
        },
        [{
            "id": line["id"], "vendor_fob_unit_usd": "20",
            "unit_weight_kg": "1", "lead_time": "4 weeks",
            "pricing_override_value": "100",
            "pricing_override_reason": "Precio autorizado",
        }],
        1,
    )
    result = QuoteManagementService.calculate(quote_id)
    quote = result["quote"]
    assert quote["calculated_dhl_zone"] == 4
    assert Decimal(quote["calculated_shipping_usd"]) == Decimal("52.35")
    assert Decimal(quote["customs_usd"]) == 0
    assert Decimal(quote["bank_fee_usd"]) == Decimal("30.00")
    assert Decimal(quote["landed_cost_usd"]) == Decimal("122.35")
    assert Decimal(quote["profit_usd"]) == Decimal("77.65")
    assert Decimal(result["lines"][0]["shipping"]) == Decimal("52.35")


def test_revisions_copy_provenance_without_overwriting(quote_database):
    quote_id = QuoteManagementService.create_from_rfq(_rfq(), 1)
    revision_id = QuoteManagementService.new_revision(quote_id, 1)
    first = QuoteManagementRepository.get(quote_id)
    second = QuoteManagementRepository.get(revision_id)
    assert first["revision"] == 1
    assert second["revision"] == 2
    assert second["revised_from_quote_id"] == quote_id
    assert second["originating_rfq_id"] == first["originating_rfq_id"]
    assert QuoteManagementRepository.lines(revision_id)[0]["source_rfq_item_id"]


def test_manual_overrides_require_reasons(quote_database):
    quote_id = QuoteManagementService.create_from_rfq(_rfq(), 1)
    line = QuoteManagementRepository.lines(quote_id)[0]
    with pytest.raises(ValueError, match="precio manual requiere"):
        QuoteManagementService.save_workspace(
            quote_id, {}, [{"id": line["id"], "pricing_override_value": "10"}], 1
        )
