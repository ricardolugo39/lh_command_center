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
