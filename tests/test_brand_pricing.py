from contextlib import contextmanager

import pytest

from app.workspace.stock_planning import pricing
from app.workspace.stock_planning.pricing import BrandPricingService


def test_thk_product_classification_uses_description_and_series():
    assert BrandPricingService._classification({
        "internal_sku": "HSR 20-3000LTHK",
        "product_name": "RIEL LINEAL",
    }) == ("RIEL", "HSR")
    assert BrandPricingService._classification({
        "internal_sku": "SHS 25 CTHK",
        "product_name": "GUIA LINEAL",
    }) == ("BLOQUE", "SHS")
    assert BrandPricingService._classification({
        "internal_sku": "BK 20THK",
        "product_name": "SOPORTE",
    }) == ("CHUMACERA", "BK")


def test_thk_ball_screw_products_use_distinct_types_and_sku_series():
    assert BrandPricingService._classification({
        "internal_sku": "BNK 1510-3THK",
        "product_name": "TUERCA DE BOLAS",
    }) == ("TUERCA DE BOLAS", "BNK")
    assert BrandPricingService._classification({
        "internal_sku": "SBN 1605-600LTHK",
        "product_name": "TORNILLO DE BOLAS",
    }) == ("TORNILLO DE BOLAS", "SBN")


def test_rail_identity_matches_equivalent_lengths():
    one_meter = BrandPricingService._rail_identity("HSR 20-1000LTHK")
    three_meter = BrandPricingService._rail_identity("HSR 20-3000LTHK")

    assert one_meter == (1000, "HSR 20-LENGTHTHK")
    assert three_meter == (3000, "HSR 20-LENGTHTHK")


def test_price_rounding_uses_nearest_configured_increment():
    assert BrandPricingService._round_price(123_449, 100) == 123_400
    assert BrandPricingService._round_price(123_450, 100) == 123_500


def test_accepted_vendor_quote_replaces_erp_fob_in_calculation():
    scenario = {
        "trm": 3800, "import_factor": 1.2,
        "rail_increment_percent": 17, "rounding_increment": 100,
    }
    rules = [{
        "product_type": "BLOQUE", "series": "HSR",
        "gross_margin_percent": 58,
    }, {
        "product_type": "OTRO", "series": "GENERAL",
        "gross_margin_percent": 58,
    }]
    products = [{
        "internal_sku": "HSR 20 ATHK", "vendor_sku": None,
        "product_name": "GUIA LINEAL", "fob_usd": 40,
        "lista1_cop": 500_000,
    }]
    quotes = {"HSR 20 ATHK": [{
        "accepted_fob_usd": 50, "accepted_at": "2026-09-17 12:00:00",
        "branch_code": "1",
    }]}

    line = BrandPricingService._calculate(
        scenario, rules, products, {}, quotes
    )[0]

    assert line["erp_fob_usd"] == 40
    assert line["quote_fob_usd"] == 50
    assert line["effective_fob_source"] == "vendor_quote"
    assert line["calculated_price_cop"] == 542_900


def test_thomson_shaft_uses_its_own_fob_without_length_increment():
    scenario = {
        "profile_code": "Thomson", "trm": 3800, "import_factor": 1.2,
        "rail_increment_percent": 17, "rounding_increment": 100,
    }
    products = [{
        "internal_sku": "W 20 H6/1500THO", "vendor_sku": None,
        "product_name": "EJE CORTADO", "fob_usd": 40,
        "lista1_cop": 500_000,
    }]
    rules = [{
        "product_type": "EJE", "series": "W",
        "gross_margin_percent": 58,
    }]

    line = BrandPricingService._calculate(
        scenario, rules, products, {}, {}
    )[0]

    assert line["product_type"] == "EJE"
    assert line["series"] == "W"
    assert line["adjusted_fob_usd"] == 40
    assert line["rail_increment_applied"] == 0
    assert line["calculated_price_cop"] == 434_300


def test_thomson_product_families_are_classified_from_name():
    assert BrandPricingService._thomson_classification({
        "internal_sku": "SUPER 16THO", "product_name": "RODAMIENTO LINEAL",
    }) == ("RODAMIENTO LINEAL", "SUPER")
    assert BrandPricingService._thomson_classification({
        "internal_sku": "LL24B020THO", "product_name": "ACTUADOR ELECTRAK",
    }) == ("ACTUADOR", "LL")
    assert BrandPricingService._thomson_classification({
        "internal_sku": "WZ 1 L/600THO", "product_name": "EJE SOPORTADO",
    }) == ("EJE", "WZ")
    assert BrandPricingService._thomson_classification({
        "internal_sku": "FNYBU 20THO", "product_name": "RODAMIENTO LINEAL",
    }) == ("RODAMIENTO LINEAL", "FNYBU")


def test_thomson_numeric_linear_guides_are_grouped_by_hundreds_series():
    assert BrandPricingService._thomson_classification({
        "internal_sku": "411 N15 A0THO", "product_name": "GUIA CUADRADA",
    }) == ("GUIA LINEAL", "400")
    assert BrandPricingService._thomson_classification({
        "internal_sku": "511 H25 D0THO", "product_name": "GUIA LINEAL",
    }) == ("GUIA LINEAL", "500")


class _ReopenConnection:
    def __init__(self, status="approved", decision_count=542):
        self.status = status
        self.decision_count = decision_count
        self.updated = False

    def execute(self, statement, parameters):
        if "SELECT status" in statement:
            return _Result({"status": self.status})
        if "UPDATE brand_pricing_scenarios" in statement:
            self.status = "draft"
            self.updated = True
            return _Result(None)
        if "SELECT COUNT(*) AS count" in statement:
            return _Result({"count": self.decision_count})
        raise AssertionError(statement)


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


def _use_connection(monkeypatch, connection):
    @contextmanager
    def fake_transaction(*, write):
        assert write is True
        yield connection

    monkeypatch.setattr(pricing, "transaction", fake_transaction)


def test_reopen_returns_scenario_to_draft_and_preserves_decisions(monkeypatch):
    connection = _ReopenConnection()
    _use_connection(monkeypatch, connection)

    count = BrandPricingService.reopen(4)

    assert count == 542
    assert connection.status == "draft"
    assert connection.updated is True


@pytest.mark.parametrize("status", ["draft", "exported"])
def test_reopen_rejects_scenarios_that_are_not_closed(monkeypatch, status):
    connection = _ReopenConnection(status=status)
    _use_connection(monkeypatch, connection)

    with pytest.raises(ValueError):
        BrandPricingService.reopen(4)

    assert connection.updated is False
