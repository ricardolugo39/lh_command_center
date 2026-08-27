from typing import Any

from app.workspace.repositories.commercial_visit_repository import (
    CommercialVisitRepository,
)
from app.workspace.timeline.entry import (
    TimelineCategory,
    TimelineEntry,
    TimelineEventType,
)
from app.workspace.timeline.providers.base import TimelineProvider


class VisitTimelineProvider(TimelineProvider):
    event_type = TimelineEventType.VISIT

    def get_events(
        self,
        project_id: int,
        records: list[dict[str, Any]] | None = None,
    ) -> list[TimelineEntry]:
        rows = (
            records
            if records is not None
            else CommercialVisitRepository.list_project(project_id)
        )
        return [self._entry(row) for row in rows]

    @classmethod
    def _entry(cls, visit: dict[str, Any]) -> TimelineEntry:
        description = (
            visit.get("executive_summary")
            or visit.get("visit_reason")
            or "Visita comercial registrada."
        )
        return TimelineEntry(
            id=f"visit-{visit['id']}",
            event_type=cls.event_type,
            icon="map-pin",
            color="neutral",
            title="Visita comercial",
            description=description,
            source="Visita",
            reference_id=visit["id"],
            date=visit.get("visit_date") or visit.get("imported_at"),
            user=visit.get("advisor_name") or "AppSheet",
            endpoint="workspace.commercial_visit_detail",
            endpoint_values={"visit_id": visit["id"]},
            category=TimelineCategory.COMMERCIAL,
            deduplication_key=f"visit:{visit['id']}",
            deduplication_priority=10,
        )
