from app.workspace.services.linear_motion_service import LinearMotionService


def test_linear_motion_service_normalizes_filter_and_builds_metrics(monkeypatch):
    repository = "app.workspace.services.linear_motion_service.LinearMotionRepository"
    monkeypatch.setattr(f"{repository}.sales_summary", lambda brand: {
        "sales_ytd": 150, "sales_previous_ytd": 100,
        "active_customers": 3, "active_products": 4,
        "documents": 5, "first_sale": "2023-01-01", "last_sale": "2026-10-01",
    })
    monkeypatch.setattr(f"{repository}.monthly_sales", lambda brand: [])
    monkeypatch.setattr(f"{repository}.family_sales", lambda brand: [{
        "brand": "THK", "family": "GUIAS", "sales_ytd": 75,
        "sales_previous_ytd": 50, "products": 2,
    }])
    monkeypatch.setattr(f"{repository}.city_sales", lambda brand: [{
        "brand": "THK", "city": "CALI", "sales": 75, "customers": 2,
    }])
    monkeypatch.setattr(f"{repository}.inventory", lambda brand: [{
        "brand": "THK", "inventory_value": 40,
    }])
    monkeypatch.setattr(f"{repository}.customer_coverage", lambda brand: {
        "buyers": 4, "with_city": 4, "with_activity": 1,
        "with_classification": 1,
    })
    monkeypatch.setattr(f"{repository}.customer_segments", lambda brand: [{
        "brand": "THK", "customer_type": "OEM", "customers": 2, "sales": 80,
    }])
    monkeypatch.setattr(f"{repository}.commercial_coverage", lambda brand: {
        "quotes": 2, "linked_projects": 1, "tagged_projects": 0,
    })
    monkeypatch.setattr(f"{repository}.diagnostic_breakdown", lambda brand, focus: {
        "components": [], "cities": [], "segments": [], "customers": [],
    })

    page = LinearMotionService.get_page("THK")

    assert page["brand"] == "THK"
    assert page["summary"]["change"] == 50
    assert page["families"][0]["change"] == 50
    assert page["coverage"]["city_percent"] == 100
    assert page["coverage"]["industry_percent"] == 25
    assert page["segments"][0]["customer_type"] == "OEM"


def test_linear_motion_service_rejects_unknown_brand(monkeypatch):
    calls = []
    repository = "app.workspace.services.linear_motion_service.LinearMotionRepository"
    monkeypatch.setattr(f"{repository}.sales_summary", lambda brand: calls.append(brand) or {})
    monkeypatch.setattr(f"{repository}.monthly_sales", lambda brand: [])
    monkeypatch.setattr(f"{repository}.family_sales", lambda brand: [])
    monkeypatch.setattr(f"{repository}.city_sales", lambda brand: [])
    monkeypatch.setattr(f"{repository}.inventory", lambda brand: [])
    monkeypatch.setattr(f"{repository}.customer_coverage", lambda brand: {})
    monkeypatch.setattr(f"{repository}.customer_segments", lambda brand: [])
    monkeypatch.setattr(f"{repository}.commercial_coverage", lambda brand: {})
    monkeypatch.setattr(f"{repository}.diagnostic_breakdown", lambda brand, focus: {
        "components": [], "cities": [], "segments": [], "customers": [],
    })

    page = LinearMotionService.get_page("Otra")

    assert page["brand"] == ""
    assert calls == [""]


def test_linear_motion_diagnosis_uses_percentage_variation(monkeypatch):
    repository = "app.workspace.services.linear_motion_service.LinearMotionRepository"
    monkeypatch.setattr(f"{repository}.sales_summary", lambda brand: {})
    monkeypatch.setattr(f"{repository}.monthly_sales", lambda brand: [])
    monkeypatch.setattr(f"{repository}.family_sales", lambda brand: [])
    monkeypatch.setattr(f"{repository}.city_sales", lambda brand: [])
    monkeypatch.setattr(f"{repository}.inventory", lambda brand: [])
    monkeypatch.setattr(f"{repository}.customer_coverage", lambda brand: {})
    monkeypatch.setattr(f"{repository}.customer_segments", lambda brand: [])
    monkeypatch.setattr(f"{repository}.commercial_coverage", lambda brand: {})
    monkeypatch.setattr(f"{repository}.diagnostic_breakdown", lambda brand, focus: {
        "components": [{"name": "Rieles", "current": 75, "previous": 100}],
        "cities": [{"name": "Cali", "current": 10, "previous": 0}],
        "segments": [], "customers": [],
    })

    page = LinearMotionService.get_page("THK", "guides")

    assert page["diagnosis"]["components"][0]["change"] == -25
    assert page["diagnosis"]["components"][0]["display_change"] == "-25.0%"
    assert page["diagnosis"]["cities"][0]["display_change"] == "Nueva"
