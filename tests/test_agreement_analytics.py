from app.workspace.services.agreement_analytics_service import (
    AgreementAnalyticsService,
)


def test_agreement_analytics_reconciles_revenue_and_matching(monkeypatch):
    repository = "app.workspace.services.agreement_analytics_service.AgreementAnalyticsRepository"
    agreement = {
        "id": 9, "customer_id": 3, "start_date": "2026-01-01",
        "end_date": "2026-12-31", "supplier": "SKF",
    }
    items = [
        {"id": 1, "internal_sku": "A1", "manufacturer_part_number": "6201", "description": "Rodamiento"},
        {"id": 2, "internal_sku": "A2", "manufacturer_part_number": "6202", "description": "Rodamiento"},
    ]
    monkeypatch.setattr(f"{repository}.get_customer", lambda customer_id: {"erp_customer_id": "C1"})
    monkeypatch.setattr(f"{repository}.list_items", lambda agreement_id: items)
    monkeypatch.setattr(f"{repository}.get_previous_agreement", lambda *args: None)
    monkeypatch.setattr(f"{repository}.list_known_product_keys", lambda erp_id: ["6201SKF"])

    def sales(erp_id, start, end):
        if start.startswith("2026"):
            return [
                {"sale_date": "2026-02-01", "product_key": "6201SKF", "family_name": "Rodamientos", "revenue": 100},
                {"sale_date": "2026-02-01", "product_key": "NO-ACUERDO", "family_name": "Otros", "revenue": 300},
            ]
        return [{"sale_date": "2025-02-01", "product_key": "6201SKF", "family_name": "Rodamientos", "revenue": 80}]

    monkeypatch.setattr(f"{repository}.list_sales", sales)
    result = AgreementAnalyticsService.get_analytics(3, agreement)

    assert result["agreement_revenue"] == 100
    assert result["account_revenue"] == 400
    assert result["share_of_account"] == 25
    assert result["coverage"] == 50
    assert result["matching_success"] == 50
    assert result["never_sold"] == 1
    assert result["lost_products"] is None
    assert result["lost_products_label"] == "Sin comparación histórica"
    assert result["priorities"]
    assert sum(point["current"] for point in result["monthly"]) == 100
    assert sum(family["revenue"] for family in result["families"]) == 100
    assert result["reference_label"] == "Referencia histórica estimada"


def test_product_filters_are_combined_and_paginated():
    rows = [
        {"status": "new", "description": "Rodamiento SKF", "internal_sku": "A1"},
        {"status": "active", "description": "Rodamiento SKF", "internal_sku": "A2"},
        {"status": "new", "description": "Cadena", "internal_sku": "B1"},
    ]

    filtered = AgreementAnalyticsService._filter_rows(rows, "rodamiento", "new")

    assert filtered == [rows[0]]
