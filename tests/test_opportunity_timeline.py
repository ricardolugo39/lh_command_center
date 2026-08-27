from app.workspace.repositories.activity_repository import ActivityRepository
from app.workspace.repositories.commercial_approval_repository import (
    CommercialApprovalRepository,
)
from app.workspace.repositories.commercial_visit_repository import (
    CommercialVisitRepository,
)
from app.workspace.repositories.project_file_repository import (
    ProjectFileRepository,
)
from app.workspace.services.opportunity_timeline_service import (
    OpportunityTimelineService,
)
from app.workspace.services.quote_service import QuoteService
from app.workspace.timeline.entry import (
    TimelineCategory,
    TimelineEntry,
    TimelineEventType,
)
from app.workspace.timeline.providers import TIMELINE_PROVIDERS
from app.workspace.timeline.providers.activity_provider import (
    ActivityTimelineProvider,
)
from app.workspace.timeline.providers.approval_provider import (
    ApprovalTimelineProvider,
)
from app.workspace.timeline.providers.file_provider import FileTimelineProvider
from app.workspace.timeline.providers.quote_provider import QuoteTimelineProvider
from app.workspace.timeline.providers.visit_provider import VisitTimelineProvider


def test_timeline_normalizes_all_mvp_sources_and_sorts_newest_first(
    monkeypatch,
):
    monkeypatch.setattr(
        ActivityRepository,
        "list_project_activities",
        lambda project_id: [
            {
                "id": 1,
                "activity_type": "meeting",
                "title": "Reunión con el cliente",
                "details": "Se revisó la propuesta.",
                "created_by": "Ana",
                "occurred_at": "2026-07-20 09:00:00",
                "created_at": "2026-07-20 09:00:00",
            }
        ],
    )
    monkeypatch.setattr(
        CommercialVisitRepository,
        "list_project",
        lambda project_id: [
            {
                "id": 2,
                "visit_date": "2026-07-21",
                "imported_at": "2026-07-21 18:00:00",
                "advisor_name": "Carlos",
                "executive_summary": "Validación técnica en planta.",
            }
        ],
    )
    monkeypatch.setattr(
        QuoteService,
        "list_project_quotes",
        lambda project_id: [
            {
                "id": 3,
                "display_quote_number": "CTC-1234",
                "display_amount": "COP 10,000.00",
                "quote_status": "Enviada",
                "quote_date": "2026-07-19",
                "created_at": "2026-07-19 08:00:00",
                "erp_user": "Diana",
            }
        ],
    )
    monkeypatch.setattr(
        CommercialApprovalRepository,
        "list_project_timeline_events",
        lambda project_id: [
            {
                "id": 4,
                "approval_id": 8,
                "event_type": "approved",
                "requested_discount": 12,
                "comments": "Aprobado por volumen.",
                "created_at": "2026-07-22 10:30:00",
                "actor": "Ricardo Lugo",
            }
        ],
    )
    monkeypatch.setattr(
        ProjectFileRepository,
        "list_project_files",
        lambda project_id: [
            {
                "id": 5,
                "original_name": "plano.pdf",
                "category": "technical",
                "created_at": "2026-07-18 12:00:00",
                "uploaded_by": "Elena",
            }
        ],
    )

    timeline = OpportunityTimelineService.get_timeline(42)

    assert [entry.event_type for entry in timeline] == [
        TimelineEventType.APPROVAL,
        TimelineEventType.VISIT,
        TimelineEventType.ACTIVITY,
        TimelineEventType.QUOTE,
        TimelineEventType.FILE,
    ]
    assert [entry.type for entry in timeline] == [
        "approval",
        "visit",
        "activity",
        "quote",
        "file",
    ]
    assert all(isinstance(entry, TimelineEntry) for entry in timeline)
    assert {entry.icon for entry in timeline} == {
        "calendar-check",
        "map-pin",
        "file-text",
        "check-circle",
        "paperclip",
    }
    assert {entry.color for entry in timeline} == {"neutral"}
    assert [entry.category for entry in timeline] == [
        TimelineCategory.SYSTEM,
        TimelineCategory.COMMERCIAL,
        TimelineCategory.COMMERCIAL,
        TimelineCategory.COMMERCIAL,
        TimelineCategory.SYSTEM,
    ]


def test_automatic_activity_is_classified_as_system_presentation():
    event = ActivityTimelineProvider().get_events(
        42,
        records=[{
            "id": 9,
            "activity_type": "status_changed",
            "title": "Estado actualizado",
            "details": "Pasó a negociación",
            "created_by": "Ana",
            "created_at": "2026-07-22",
        }],
    )[0]

    assert event.category is TimelineCategory.SYSTEM


def test_timeline_does_not_duplicate_visits_or_approvals_mirrored_as_activities(
    monkeypatch,
):
    monkeypatch.setattr(
        ActivityRepository,
        "list_project_activities",
        lambda project_id: [
            {
                "id": 1,
                "activity_type": "visit",
                "title": "Visita comercial",
                "details": "Detalle\n[visita:20]",
                "created_by": "AppSheet",
                "occurred_at": "2026-07-20",
                "created_at": "2026-07-20",
            },
            {
                "id": 2,
                "activity_type": "commercial_approval_approved",
                "title": "Descuento comercial aprobado",
                "details": "AP-000030",
                "created_by": "Ricardo Lugo",
                "occurred_at": "2026-07-21",
                "created_at": "2026-07-21",
            },
        ],
    )
    monkeypatch.setattr(
        CommercialVisitRepository,
        "list_project",
        lambda project_id: [
            {
                "id": 20,
                "visit_date": "2026-07-20",
                "advisor_name": "Ana",
                "visit_reason": "Seguimiento",
            }
        ],
    )
    monkeypatch.setattr(QuoteService, "list_project_quotes", lambda project_id: [])
    monkeypatch.setattr(
        CommercialApprovalRepository,
        "list_project_timeline_events",
        lambda project_id: [
            {
                "id": 3,
                "approval_id": 30,
                "event_type": "approved",
                "requested_discount": 10,
                "created_at": "2026-07-21",
                "actor": "Ricardo Lugo",
            }
        ],
    )
    monkeypatch.setattr(
        ProjectFileRepository,
        "list_project_files",
        lambda project_id: [],
    )

    timeline = OpportunityTimelineService.get_timeline(42)

    assert [entry.id for entry in timeline] == [
        "approval-3",
        "visit-20",
    ]


def test_timeline_keeps_manual_visit_activity_as_activity(monkeypatch):
    monkeypatch.setattr(
        ActivityRepository,
        "list_project_activities",
        lambda project_id: [
            {
                "id": 7,
                "activity_type": "visit",
                "title": "Visita registrada manualmente",
                "details": "Seguimiento comercial",
                "created_by": "Ana",
                "occurred_at": "2026-07-20",
                "created_at": "2026-07-20",
            }
        ],
    )
    monkeypatch.setattr(
        CommercialVisitRepository, "list_project", lambda project_id: []
    )
    monkeypatch.setattr(QuoteService, "list_project_quotes", lambda project_id: [])
    monkeypatch.setattr(
        CommercialApprovalRepository,
        "list_project_timeline_events",
        lambda project_id: [],
    )
    monkeypatch.setattr(
        ProjectFileRepository,
        "list_project_files",
        lambda project_id: [],
    )

    timeline = OpportunityTimelineService.get_timeline(42)

    assert timeline[0].event_type is TimelineEventType.ACTIVITY
    assert timeline[0].reference_id == 7


def test_every_registered_provider_returns_timeline_entries():
    records = {
        TimelineEventType.ACTIVITY: [{
            "id": 1, "activity_type": "meeting", "title": "Reunión",
            "details": "Detalle", "created_by": "Ana",
            "occurred_at": "2026-07-20", "created_at": "2026-07-20",
        }],
        TimelineEventType.VISIT: [{
            "id": 2, "visit_date": "2026-07-20", "advisor_name": "Ana",
            "visit_reason": "Seguimiento",
        }],
        TimelineEventType.QUOTE: [{
            "id": 3, "display_quote_number": "CTC-1",
            "display_amount": "COP 1.00", "quote_date": "2026-07-20",
        }],
        TimelineEventType.APPROVAL: [{
            "id": 4, "approval_id": 5, "event_type": "created",
            "created_at": "2026-07-20", "actor": "Ana",
        }],
        TimelineEventType.FILE: [{
            "id": 6, "original_name": "archivo.pdf",
            "created_at": "2026-07-20",
        }],
    }

    assert len(TIMELINE_PROVIDERS) == 5
    for provider in TIMELINE_PROVIDERS:
        events = provider.get_events(42, records=records[provider.event_type])
        assert len(events) == 1
        assert isinstance(events[0], TimelineEntry)
        assert events[0].event_type is provider.event_type


def test_each_provider_queries_only_its_own_source(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ActivityRepository,
        "list_project_activities",
        lambda project_id: calls.append("activity") or [],
    )
    monkeypatch.setattr(
        CommercialVisitRepository,
        "list_project",
        lambda project_id: calls.append("visit") or [],
    )
    monkeypatch.setattr(
        QuoteService,
        "list_project_quotes",
        lambda project_id: calls.append("quote") or [],
    )
    monkeypatch.setattr(
        CommercialApprovalRepository,
        "list_project_timeline_events",
        lambda project_id: calls.append("approval") or [],
    )
    monkeypatch.setattr(
        ProjectFileRepository,
        "list_project_files",
        lambda project_id: calls.append("file") or [],
    )

    provider_expectations = [
        (ActivityTimelineProvider(), "activity"),
        (VisitTimelineProvider(), "visit"),
        (QuoteTimelineProvider(), "quote"),
        (ApprovalTimelineProvider(), "approval"),
        (FileTimelineProvider(), "file"),
    ]
    for provider, expected in provider_expectations:
        calls.clear()
        provider.get_events(42)
        assert calls == [expected]


def test_service_aggregates_registered_providers_without_source_knowledge(
    monkeypatch,
):
    class Provider:
        def __init__(self, event):
            self.event_type = event.event_type
            self.event = event

        def get_events(self, project_id, records=None):
            assert project_id == 42
            return [self.event]

    older = TimelineEntry(
        id="future-1", event_type=TimelineEventType.ACTIVITY,
        icon="calendar-check", color="neutral", title="Anterior",
        description="", source="Future", reference_id=1,
        date="2026-07-20", user="Sistema", endpoint="workspace.project_detail",
    )
    newer = TimelineEntry(
        id="future-2", event_type=TimelineEventType.FILE,
        icon="paperclip", color="neutral", title="Nuevo",
        description="", source="Future", reference_id=2,
        date="2026-07-22", user="Sistema", endpoint="workspace.project_detail",
    )
    monkeypatch.setattr(
        OpportunityTimelineService,
        "providers",
        (Provider(older), Provider(newer)),
    )

    result = OpportunityTimelineService.get_timeline(42)

    assert [event.id for event in result] == ["future-2", "future-1"]
