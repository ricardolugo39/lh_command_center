from datetime import date

from app.workspace.services.company_sales_dashboard_service import CompanySalesDashboardService


def _sale(year, value, office, customer, seller):
    return {
        "sale_date": f"{year}-01-10", "prefijo": "FV", "numero": f"{year}-{customer}",
        "product_id": "6204SKF", "product_name": "Rodamiento", "family_name": "RODAMIENTOS",
        "cantidad": 1, "neto": value, "customer_id": customer,
        "customer_name": customer, "sales_rep": seller, "office": office,
    }


def test_company_dashboard_separates_offices_and_preserves_consolidated_total(monkeypatch):
    rows = [
        _sale(2025, 100, "Bogotá", "A", "BOG REP"),
        _sale(2026, 80, "Bogotá", "A", "BOG REP"),
        _sale(2025, 50, "Cali", "B", "CALI REP"),
        _sale(2026, 70, "Cali", "B", "CALI REP"),
    ]
    monkeypatch.setattr(
        "app.workspace.services.company_sales_dashboard_service.CompanySalesRepository.list_history",
        lambda office="": [r for r in rows if not office or r["office"] == office],
    )
    monkeypatch.setattr(
        "app.workspace.services.company_sales_dashboard_service.date",
        type("FixedDate", (), {"today": staticmethod(lambda: date(2026, 8, 10)), "fromisoformat": staticmethod(date.fromisoformat)}),
    )

    page = CompanySalesDashboardService.get_page()

    assert page["diagnosis"]["delta"] == 0
    assert sum(item["current"] for item in page["office_summary"]) == 150
    assert page["office_summary"][0]["display_delta"] == "-COP 20"
    assert page["office_summary"][1]["display_delta"] == "+COP 20"
