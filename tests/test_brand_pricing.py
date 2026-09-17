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
