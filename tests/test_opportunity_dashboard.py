from datetime import date

from app.workspace.repositories.commercial_approval_repository import (
    CommercialApprovalRepository,
)
from app.workspace.services.opportunity_dashboard_service import (
    OpportunityDashboard,
    OpportunityDashboardService,
)
from app.workspace.services.opportunity_list_service import OpportunityListService
from app.workspace.timeline.entry import TimelineEntry, TimelineEventType


def _event(
    event_id: str,
    event_type: TimelineEventType,
    event_date: str,
    title: str,
) -> TimelineEntry:
    return TimelineEntry(
        id=event_id,
        event_type=event_type,
        icon="calendar-check",
        color="neutral",
        title=title,
        description="",
        source="Prueba",
        reference_id=1,
        date=event_date,
        user="Ana",
        endpoint="workspace.project_detail",
    )


def test_dashboard_aggregates_existing_opportunity_data(monkeypatch):
    metric_calls = []
    monkeypatch.setattr(
        CommercialApprovalRepository,
        "get_metrics",
        lambda project_id: metric_calls.append(project_id) or {"pending": 2},
    )
    timeline = [
        _event("file-1", TimelineEventType.FILE, "2026-07-22", "Plano cargado"),
        _event("visit-1", TimelineEventType.VISIT, "2026-07-20", "Visita comercial"),
        _event("activity-1", TimelineEventType.ACTIVITY, "2026-07-18", "Reunión"),
        _event("quote-1", TimelineEventType.QUOTE, "2026-07-17", "Cotización CTC-1"),
    ]

    dashboard = OpportunityDashboardService.get_dashboard(
        opportunity={
            "id": 42,
            "name": "Nueva línea",
            "status": "negotiation",
            "sales_rep": "Ana",
            "current_blocker": "Validación técnica",
            "commercial_amount": "2500000",
            "commercial_currency": "COP",
            "updated_at": "2026-07-22 11:00:00",
            "created_at": "2026-07-01 09:00:00",
        },
        customer={"name": "Cliente Industrial"},
        timeline=timeline,
        followups=[
            {
                "status": "pending",
                "due_date": "2026-07-24",
                "description": "Enviar muestra",
            },
            {"status": "completed", "due_date": "2026-07-10"},
        ],
        quotes=[
            {
                "quote_status": "Abierto",
                "amount": 2500000,
                "currency_code": "COP",
            },
            {"quote_status": "Cerrada", "amount": 100},
        ],
        files=[{"id": 1}, {"id": 2}],
        approval={"status_label": "Pendiente de aprobación", "probability": 70},
        today=date(2026, 7, 22),
    )

    assert isinstance(dashboard, OpportunityDashboard)
    assert metric_calls == [42]
    assert dashboard.health["key"] == "green"
    assert dashboard.counts == {
        "pending_approvals": 2,
        "open_quotes": 1,
        "open_followups": 1,
        "overdue_followups": 0,
        "files": 2,
    }
    assert dashboard.derived_dates["last_activity"] == "2026-07-20"
    assert dashboard.derived_dates["last_visit"] == "2026-07-20"
    assert dashboard.derived_dates["last_quote"] == "2026-07-17"
    assert dashboard.derived_dates["latest_movement"] == "2026-07-22"
    assert dashboard.derived_dates["days_since_activity"] == 2
    assert dashboard.derived_dates["days_since_visit"] == 2
    assert dashboard.derived_dates["next_followup"] == "2026-07-24"
    assert dashboard.derived_dates["opened_at"] == "2026-07-01"
    assert dashboard.derived_dates["days_open"] == 21
    assert dashboard.derived_dates["open_age_label"] == "Abierta hace 21 días"
    assert [event.id for event in dashboard.latest_events] == [
        "file-1",
        "visit-1",
        "activity-1",
    ]
    metrics = {item["label"]: item for item in dashboard.summary_metrics}
    assert set(metrics) == {
        "Estado actual",
        "Salud",
        "Bloqueo actual",
        "Responsable",
        "Última actividad",
        "Probabilidad",
    }
    assert metrics["Responsable"]["value"] == "Ana"
    assert metrics["Probabilidad"]["value"] == "70%"
    assert metrics["Bloqueo actual"]["value"] == "Validación técnica"
    assert dashboard.commercial_value == (
        OpportunityListService.present_commercial_value(
            {"commercial_amount": "2500000", "commercial_currency": "COP"},
            None,
        )
    )


def test_health_thresholds_are_centralized():
    assert OpportunityDashboardService.calculate_health(
        days_since_activity=14, has_overdue_followups=False
    )["key"] == "green"
    assert OpportunityDashboardService.calculate_health(
        days_since_activity=15, has_overdue_followups=False
    )["key"] == "yellow"
    assert OpportunityDashboardService.calculate_health(
        days_since_activity=29, has_overdue_followups=False
    )["key"] == "yellow"
    assert OpportunityDashboardService.calculate_health(
        days_since_activity=30, has_overdue_followups=False
    )["key"] == "red"
    assert OpportunityDashboardService.calculate_health(
        days_since_activity=None, has_overdue_followups=False
    )["key"] == "red"


def test_overdue_followup_prevents_green_health():
    health = OpportunityDashboardService.calculate_health(
        days_since_activity=1,
        has_overdue_followups=True,
    )

    assert health["key"] == "yellow"
    assert health["detail"] == "Tiene follow-ups vencidos"


def test_dashboard_hides_probability_when_it_has_no_value(monkeypatch):
    monkeypatch.setattr(
        CommercialApprovalRepository,
        "get_metrics",
        lambda project_id: {"pending": 0},
    )

    dashboard = OpportunityDashboardService.get_dashboard(
        opportunity={"id": 42, "status": "negotiation"},
        customer={"name": "Cliente"},
        timeline=[],
        followups=[],
        quotes=[],
        files=[],
        approval=None,
    )

    assert "Probabilidad" not in {
        metric["label"] for metric in dashboard.summary_metrics
    }


def test_dashboard_uses_list_value_fallback_for_quote(monkeypatch):
    monkeypatch.setattr(
        CommercialApprovalRepository,
        "get_metrics",
        lambda project_id: {"pending": 0},
    )
    quote = {
        "display_amount": "USD 1,250.00",
        "display_quote_number": "CTC-18",
    }

    dashboard = OpportunityDashboardService.get_dashboard(
        opportunity={"id": 42, "status": "negotiation"},
        customer={"name": "Cliente"},
        timeline=[],
        followups=[],
        quotes=[quote],
        files=[],
        approval=None,
    )

    expected = OpportunityListService.present_commercial_value(
        {"id": 42, "status": "negotiation"},
        quote,
    )
    assert dashboard.commercial_value == expected
    assert "Valor comercial" not in {
        metric["label"] for metric in dashboard.summary_metrics
    }


def test_crm_source_date_drives_open_age(monkeypatch):
    monkeypatch.setattr(
        CommercialApprovalRepository, "get_metrics", lambda project_id: {"pending": 0}
    )
    dashboard = OpportunityDashboardService.get_dashboard(
        opportunity={
            "id": 42, "status": "prospect", "created_at": "2026-07-20",
            "crm_source": {"date": "2026-06-01"},
        },
        customer={"name": "Cliente"}, timeline=[], followups=[], quotes=[],
        files=[], approval=None, today=date(2026, 7, 22),
    )
    assert dashboard.derived_dates["opened_at"] == "2026-06-01"
    assert dashboard.derived_dates["days_open"] == 51
