from app.workspace.services.customer_portfolio_service import (
    CustomerPortfolioService,
)


def test_dashboard_uses_server_side_portfolio_and_bulk_coverage(monkeypatch):
    repository = "app.workspace.services.customer_portfolio_service.CustomerPortfolioRepository"
    captured = {}

    def list_portfolio(**kwargs):
        captured.update(kwargs)
        return [{
            "erp_customer_id": "9001", "customer_name": "Cliente sin proyecto",
            "workspace_id": None, "revenue_ytd": 0, "revenue_ly": 0,
            "open_opportunities": 0, "open_quotes": 0, "last_activity": "",
            "active_agreements": 0, "agreement_id": None,
            "filtered_total": 101,
        }]

    monkeypatch.setattr(f"{repository}.list_portfolio", list_portfolio)
    monkeypatch.setattr(f"{repository}.get_coverage", lambda ids: {})
    monkeypatch.setattr(f"{repository}.get_dimensions", lambda: {"offices": ["Cali", "Bogotá"], "advisors": ["Ana"]})
    monkeypatch.setattr(f"{repository}.get_statistics", lambda **kwargs: {
        "total": 101, "strategic": 2, "agreement": 1, "no_agreement": 100,
        "inactive": 99, "risk": 98, "opportunities": 1, "no_sales": 100,
        "open_opportunities": 3, "revenue_ytd": 500,
    })

    page = CustomerPortfolioService.get_dashboard(
        search="Cliente", quick_filter="no_sales", sort="sales",
        direction="asc", page=2,
    )

    assert page["customers"][0]["customer_name"] == "Cliente sin proyecto"
    assert captured["offset"] == CustomerPortfolioService.PAGE_SIZE
    assert captured["quick_filter"] == "no_sales"
    assert page["pagination"]["pages"] == 5
    assert page["kpis"][0] == ("Clientes totales", 101)


def test_health_and_next_action_rules_are_centralized():
    assert CustomerPortfolioService._status(0, 100, 20, 20)["label"] == "En riesgo"
    assert CustomerPortfolioService._status(120, 100, 10, 10, 1)["label"] == "Excelente"
    assert CustomerPortfolioService._status(90, 100, 70, 20)["label"] == "Atención"

    followup = CustomerPortfolioService._next_action({
        "next_followup": "Llamar al cliente", "next_followup_date": "2026-08-01",
    }, 10, 10)
    dormant = CustomerPortfolioService._next_action({
        "open_quotes": 0, "open_opportunities": 0,
    }, 80, 20)

    assert followup["label"] == "Llamar al cliente"
    assert dormant["label"] == "Programar visita"


def test_days_without_purchase_drive_health_and_display():
    row = {
        "customer_name": "Cliente", "revenue_ytd": 100, "revenue_ly": 100,
        "last_purchase_date": None, "last_activity": "2026-07-01",
        "open_opportunities": 0, "active_agreements": 0,
    }

    customer = CustomerPortfolioService._present(row)

    assert customer["purchase_days_label"] == "Nunca"
    assert customer["purchase_tone"] == "critical"
    assert customer["status"]["label"] == "En riesgo"


def test_revenue_compact_formatting():
    assert CustomerPortfolioService._format_compact_cop(1_200_000_000) == "COP 1.20 B"
    assert CustomerPortfolioService._format_compact_cop(465_300_000) == "COP 465.3 M"
    assert CustomerPortfolioService._format_compact_cop(52_800_000) == "COP 52.8 M"
