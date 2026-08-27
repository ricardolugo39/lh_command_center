from app.workspace.services.strategic_account_service import (
    StrategicAccountService,
)


def test_overview_orchestrates_real_and_temporary_data(monkeypatch):
    repository = "app.workspace.services.strategic_account_service.StrategicAccountRepository"
    monkeypatch.setattr(
        f"{repository}.get_account",
        lambda customer_id: {
            "id": customer_id,
            "name": "Cliente Uno",
            "erp_customer_id": "123",
            "sales_rep": "Ana",
        },
    )
    monkeypatch.setattr(f"{repository}.get_agreement", lambda customer_id: None)
    monkeypatch.setattr(
        f"{repository}.get_sales_summary",
        lambda erp_id: {"revenue_ytd": 150, "revenue_previous_ytd": 100},
    )
    monkeypatch.setattr(
        f"{repository}.list_monthly_sales",
        lambda erp_id: [
            {"month_number": 1, "period": "current", "revenue": 150},
            {"month_number": 1, "period": "previous", "revenue": 100},
        ],
    )
    monkeypatch.setattr(f"{repository}.list_top_product_families", lambda erp_id: [])
    monkeypatch.setattr(
        f"{repository}.get_activity_summary",
        lambda customer_id: {
            "visits": 2,
            "meetings": 1,
            "quotes": 3,
            "last_meaningful_activity": "2026-07-20",
        },
    )
    monkeypatch.setattr(
        f"{repository}.list_opportunities",
        lambda customer_id: [{"id": 1, "name": "Expansión", "status": "prospect", "amount": 500}],
    )
    monkeypatch.setattr(f"{repository}.list_recent_activities", lambda customer_id: [])

    page = StrategicAccountService.get_overview(7)

    assert page["account"]["name"] == "Cliente Uno"
    assert page["agreement"]["is_temporary"] is True
    assert page["kpis"][0]["value"] == "COP 150"
    assert page["kpis"][0]["trend"] == "+50.0%"
    assert page["kpis"][1]["value"] == "1"
    assert page["activity_metrics"][0] == ("Visitas", 2)
    assert page["revenue_comparison"]["has_previous"] is True
    assert page["executive_summary"][0]["label"] == "Estado de cuenta"


def test_overview_rejects_unknown_customer(monkeypatch):
    monkeypatch.setattr(
        "app.workspace.services.strategic_account_service.StrategicAccountRepository.get_account",
        lambda customer_id: None,
    )

    try:
        StrategicAccountService.get_overview(999)
    except ValueError as error:
        assert "999" in str(error)
    else:
        raise AssertionError("Expected an unknown customer error")


def test_provisional_health_states():
    engagement = {"status": "Alta", "days_since": 2}
    healthy = StrategicAccountService._provisional_health(
        has_sales=True,
        growth=3,
        pipeline_value=100,
        engagement=engagement,
    )
    attention = StrategicAccountService._provisional_health(
        has_sales=True,
        growth=-5,
        pipeline_value=0,
        engagement={"status": "Baja", "days_since": 60},
    )
    sparse = StrategicAccountService._provisional_health(
        has_sales=False,
        growth=None,
        pipeline_value=0,
        engagement={"status": "Sin registro", "days_since": None},
    )

    assert healthy["label"] == "Saludable"
    assert attention["label"] == "Atención"
    assert sparse["label"] == "Sin información suficiente"


def test_product_family_share_and_comparable_growth():
    families = StrategicAccountService._product_families([
        {"family_name": "A", "revenue": 75, "previous_revenue": 50},
        {"family_name": "B", "revenue": 25, "previous_revenue": 0},
    ])

    assert families[0]["share"] == 75
    assert families[0]["growth_label"] == "+50.0%"
    assert families[1]["share"] == 25
    assert families[1]["growth_label"] is None


def test_engagement_ignores_system_events_as_customer_interaction():
    engagement = StrategicAccountService._engagement({
        "last_meaningful_activity": None,
        "last_activity": "2026-07-20",
    })

    assert engagement["status"] == "Sin registro"
    assert engagement["activity_context"] == "Actividad registrada"
    assert engagement["days_since"] is None


def test_repetitive_system_activity_is_grouped():
    rows = [
        {
            "activity_type": "status_changed",
            "title": "Estado actualizado",
            "occurred_at": "2026-07-20",
            "project_name": "Proyecto",
        },
        {
            "activity_type": "status_changed",
            "title": "Estado actualizado",
            "occurred_at": "2026-07-19",
            "project_name": "Proyecto",
        },
    ]

    result = StrategicAccountService._meaningful_recent_activity(rows)

    assert len(result) == 1
    assert result[0]["title"].startswith("2 eventos")
    assert result[0]["context_label"] == "Evento del sistema"
