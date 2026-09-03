import json
import sqlite3
from decimal import Decimal

import pytest

from app.database.migrations import upgrade
from app.workspace.repositories.quote_management_repository import QuoteManagementRepository
from app.workspace.services.quote_management_service import QuoteManagementService
from app.workspace.services.rfq_service import RFQService
from app.workspace.services.quote_weight_research_service import (
    QuoteWeightResearchService,
)
from app.workspace.services.rfq_weight_research_service import (
    RFQWeightResearchService,
)


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


def test_direct_quote_uses_same_usd_processor_without_rfq(quote_database):
    quote_id = QuoteManagementService.create_direct({
        "customer_id": 1,
        "sales_rep_name": "Asesor Externo",
        "sales_rep_email": "asesor@example.com",
        "comments": "Precio consultado en plataforma",
        "items": [{
            "reference": "ABC-123", "brand": "Otra Marca",
            "quantity": "2", "fob_unit_usd": "125.50",
            "unit_weight_kg": "1.25", "lead_time": "3 weeks",
            "source_note": "Portal del fabricante", "product_type": "BRG",
        }],
    }, 1)
    page = QuoteManagementService.workspace(quote_id)
    assert page["quote"]["originating_rfq_id"] is None
    assert page["quote"]["currency_code"] == "USD"
    assert page["quote"]["sales_rep_email"] == "asesor@example.com"
    assert page["lines"][0]["brand"] == "Otra Marca"
    assert page["lines"][0]["vendor_fob_unit_usd"] == "125.5"


def test_ai_weight_search_is_scored_saved_and_explicitly_accepted(
    quote_database, monkeypatch,
):
    quote_id = QuoteManagementService.create_from_rfq(_rfq(), 1)
    line = QuoteManagementRepository.lines(quote_id)[0]
    monkeypatch.setattr(
        "app.workspace.services.quote_weight_research_service.resolve_settings",
        lambda names: ({"OPENAI_API_KEY": "test", "OPENAI_WEIGHT_MODEL": "test-model"}, {}),
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            result = json.dumps({
                "unit_weight_kg": 1.234, "match_level": "exact",
                "calculation_method": "direct", "explanation": "Ficha oficial",
                "warning": None, "sources": [{
                    "title": "THK SR20W", "url": "https://www.thk.com/sr20w",
                    "source_type": "official_manufacturer", "evidence": "1.234 kg",
                }],
            })
            return {
                "output": [
                    {"type": "web_search_call", "action": {"sources": [
                        {"url": "https://www.thk.com/sr20w"},
                    ]}},
                    {"type": "message", "content": [
                        {"type": "output_text", "text": result, "annotations": []},
                    ]},
                ],
            }

    monkeypatch.setattr(
        "app.workspace.services.quote_weight_research_service.requests.post",
        lambda *args, **kwargs: Response(),
    )
    research_id = QuoteWeightResearchService.search(quote_id, line["id"], 1)
    proposed = QuoteManagementService.workspace(quote_id)["weight_research"][line["id"]]
    assert proposed["confidence_score"] == 99
    assert proposed["unit_weight_kg"] == "1.234"
    assert QuoteManagementRepository.line(quote_id, line["id"])["unit_weight_kg"] is None
    QuoteWeightResearchService.accept(quote_id, line["id"], research_id, 1)
    assert QuoteManagementRepository.line(quote_id, line["id"])["unit_weight_kg"] == "1.234"


def test_weight_search_prompt_requires_official_family_fallback():
    prompt = QuoteWeightResearchService._prompt({
        "brand": "Thomson", "part_number": "LL24B020-0200LEXAMMSD",
    })
    assert "thomsonlinear.com" in prompt
    assert "ordering key" in prompt
    assert "interpolación lineal" in prompt
    assert "carga/capacidad" in prompt


def test_thomson_electrak_ll_uses_audited_family_fallback(monkeypatch):
    monkeypatch.setattr(
        "app.workspace.services.quote_weight_research_service.resolve_settings",
        lambda names: ({"OPENAI_API_KEY": "test", "OPENAI_WEIGHT_MODEL": "test-model"}, {}),
    )

    class EmptyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"output_text": json.dumps({
                "unit_weight_kg": None, "match_level": "none",
                "calculation_method": "none", "explanation": None,
                "warning": None, "sources": [],
            })}

    monkeypatch.setattr(
        "app.workspace.services.quote_weight_research_service.requests.post",
        lambda *args, **kwargs: EmptyResponse(),
    )
    result = QuoteWeightResearchService.research_product(
        "Thomson", "LL24B020-0200LEXAMMSD",
        "https://www.thomsonlinear.com/en/product/LL24B020-0200LEXAMMSD",
    )
    assert result["unit_weight_kg"] == "7.514"
    assert result["calculation_method"] == "interpolated"
    assert result["confidence_score"] == 85
    assert len(result["sources"]) == 2


def test_rfq_weight_acceptance_updates_existing_draft_quote(
    quote_database, monkeypatch,
):
    rfq_id = _rfq()
    quote_id = QuoteManagementService.create_from_rfq(rfq_id, 1)
    item = RFQService.detail(rfq_id)["items"][0]
    monkeypatch.setattr(
        QuoteWeightResearchService, "research_product",
        lambda *args, **kwargs: {
            "unit_weight_kg": "7.514", "confidence_score": 85,
            "confidence_label": "Media", "source_type": "official_manufacturer",
            "match_level": "family", "calculation_method": "interpolated",
            "explanation": "Cálculo oficial", "warning": "Sin empaque",
            "sources": [], "model": "test",
        },
    )
    research_id = RFQWeightResearchService.search(rfq_id, item["id"], 1)
    RFQWeightResearchService.accept(rfq_id, item["id"], research_id, 1)
    assert RFQService.detail(rfq_id)["items"][0]["unit_weight_kg"] == "7.514"
    assert QuoteManagementRepository.lines(quote_id)[0]["unit_weight_kg"] == "7.514"
    quote_research = QuoteManagementService.workspace(quote_id)["weight_research"]
    assert quote_research[QuoteManagementRepository.lines(quote_id)[0]["id"]][
        "status"
    ] == "accepted"


def test_vendor_values_saved_after_conversion_sync_to_draft_quote(quote_database):
    rfq_id = _rfq()
    quote_id = QuoteManagementService.create_from_rfq(rfq_id, 1)
    item = RFQService.detail(rfq_id)["items"][0]
    RFQService.record_vendor_response(rfq_id, item["id"], {
        "vendor_response_status": "complete",
        "fob_unit_usd": "917.86", "unit_weight_kg": "7.514",
        "lead_time": "3-4 semanas",
    }, 1)
    line = QuoteManagementRepository.lines(quote_id)[0]
    assert line["vendor_fob_unit_usd"] == "917.86"
    assert line["unit_weight_kg"] == "7.514"
    assert line["lead_time"] == "3-4 semanas"


def test_dhl_customs_bank_and_allocations_are_decimal_safe(quote_database):
    quote_id = QuoteManagementService.create_from_rfq(_rfq(), 1)
    line = QuoteManagementRepository.lines(quote_id)[0]
    QuoteManagementService.save_workspace(
        quote_id,
        {
            "origin_option": "BR|default",
        },
        [{
            "id": line["id"], "vendor_fob_unit_usd": "20",
            "unit_weight_kg": "1", "lead_time": "4 weeks",
            "product_type": "SCREW",
        }],
        1,
    )
    result = QuoteManagementService.calculate(quote_id)
    quote = result["quote"]
    assert quote["calculated_dhl_zone"] == 4
    assert Decimal(quote["calculated_shipping_usd"]) == Decimal("65.11")
    assert Decimal(quote["customs_usd"]) == 0
    assert Decimal(quote["bank_fee_usd"]) == Decimal("30.00")
    assert Decimal(quote["landed_cost_usd"]) == Decimal("143.11")
    assert Decimal(quote["profit_usd"]) == Decimal(str(quote["amount"])) - Decimal("143.11")
    assert Decimal(result["lines"][0]["shipping"]) == Decimal("65.11")


def test_customs_is_fixed_300_usd_over_value_threshold(quote_database):
    quote_id = QuoteManagementService.create_from_rfq(_rfq(), 1)
    line = QuoteManagementRepository.lines(quote_id)[0]
    QuoteManagementService.save_workspace(
        quote_id,
        {"origin_option": "BR|default"},
        [{
            "id": line["id"], "vendor_fob_unit_usd": "1001",
            "unit_weight_kg": "1", "lead_time": "4 weeks",
            "product_type": "SCREW",
        }],
        1,
    )
    result = QuoteManagementService.calculate(quote_id)
    assert Decimal(result["quote"]["customs_usd"]) == Decimal("300.00")
    assert result["quote"]["exchange_rate"] == 1
    assert result["quote"]["normalized_amount"] == result["quote"]["amount"]


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


def test_price_is_automatic_when_product_type_is_selected(quote_database):
    quote_id = QuoteManagementService.create_from_rfq(_rfq(), 1)
    line = QuoteManagementRepository.lines(quote_id)[0]
    QuoteManagementService.save_workspace(
        quote_id, {"origin_option": "BR|default"}, [{
            "id": line["id"], "vendor_fob_unit_usd": "20",
            "unit_weight_kg": "1", "lead_time": "4 weeks",
            "product_type": "SCREW",
        }], 1
    )
    automatic = QuoteManagementService.calculate(quote_id)
    assert Decimal(automatic["lines"][0]["selling_unit"]) > 0


def test_sheet_product_factors_and_free_divisor(quote_database):
    quote_id = QuoteManagementService.create_from_rfq(_rfq(), 1)
    line = QuoteManagementRepository.lines(quote_id)[0]
    common = {
        "id": line["id"], "vendor_fob_unit_usd": "20",
        "unit_weight_kg": "1", "lead_time": "4 weeks",
    }
    QuoteManagementService.save_workspace(
        quote_id, {"origin_option": "BR|default"},
        [{**common, "product_type": "SCREW"}], 1,
    )
    screw = Decimal(QuoteManagementService.calculate(quote_id)["lines"][0]["selling_unit"])
    QuoteManagementService.save_workspace(
        quote_id, {"origin_option": "BR|default"}, [{**common, "product_type": "BLOCK"}], 1,
    )
    block = Decimal(QuoteManagementService.calculate(quote_id)["lines"][0]["selling_unit"])
    assert block > screw
    QuoteManagementService.save_workspace(
        quote_id, {"origin_option": "BR|default"},
        [{**common, "product_type": "FREE", "pricing_override_value": "0.70"}], 1,
    )
    free = QuoteManagementService.calculate(quote_id)
    assert Decimal(free["lines"][0]["selling_unit"]) == Decimal("104.63")


def test_sales_recipient_directory_is_seeded_and_extendable(quote_database):
    recipients = QuoteManagementRepository.sales_recipients()
    assert any(row["email"] == "juancarlos.benavides@lugohermanos.com" for row in recipients)
    recipient_id = QuoteManagementRepository.create_sales_recipient(
        "Nueva Vendedora", "nueva@example.com", 1
    )
    assert recipient_id
    assert QuoteManagementRepository.sales_recipient_by_email("NUEVA@example.com")["display_name"] == "Nueva Vendedora"


def test_pdf_is_written_to_persistent_data_directory(
    quote_database, tmp_path, monkeypatch,
):
    persistent = tmp_path / "persistent"
    monkeypatch.setenv("APP_DATA_DIR", str(persistent))
    quote_id = QuoteManagementService.create_from_rfq(_rfq(), 1)
    line = QuoteManagementRepository.lines(quote_id)[0]
    QuoteManagementService.save_workspace(
        quote_id, {"origin_option": "BR|default"}, [{
            "id": line["id"], "vendor_fob_unit_usd": "20",
            "unit_weight_kg": "1", "lead_time": "4 weeks",
            "product_type": "SCREW",
        }], 1,
    )
    path = QuoteManagementService.generate_pdf(quote_id, 1)
    assert path.is_file()
    assert path.parent == persistent / "pdf"
    path.unlink()
    assert QuoteManagementService.workspace(quote_id)["pdf"] is None


def test_manual_shipping_is_the_only_freight_override(quote_database):
    quote_id = QuoteManagementService.create_from_rfq(_rfq(), 1)
    line = QuoteManagementRepository.lines(quote_id)[0]
    QuoteManagementService.save_workspace(
        quote_id,
        {"origin_option": "BR|default", "manual_shipping_usd": "25"},
        [{
            "id": line["id"], "vendor_fob_unit_usd": "20",
            "unit_weight_kg": "1", "lead_time": "4 weeks",
            "product_type": "SCREW",
        }],
        1,
    )
    result = QuoteManagementService.calculate(quote_id)
    assert Decimal(result["quote"]["calculated_shipping_usd"]) == Decimal("65.11")
    assert Decimal(result["quote"]["final_shipping_usd"]) == Decimal("25.00")
    assert result["quote"]["final_dhl_zone"] == 4
