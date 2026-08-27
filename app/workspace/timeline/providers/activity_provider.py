import re
from typing import Any

from app.workspace.constants.activity_types import ActivityType
from app.workspace.repositories.activity_repository import ActivityRepository
from app.workspace.timeline.entry import (
    TimelineCategory,
    TimelineEntry,
    TimelineEventType,
)
from app.workspace.timeline.providers.base import TimelineProvider


class ActivityTimelineProvider(TimelineProvider):
    event_type = TimelineEventType.ACTIVITY
    _APPROVAL_EVENTS = {
        ActivityType.APPROVAL_CREATED: "created",
        ActivityType.APPROVAL_SUBMITTED: "submitted",
        ActivityType.APPROVAL_APPROVED: "approved",
        ActivityType.APPROVAL_RETURNED: "returned",
        ActivityType.APPROVAL_REJECTED: "rejected",
        ActivityType.APPROVAL_CANCELLED: "cancelled",
    }
    _LEGACY_ICONS = {
        ActivityType.APPROVAL_CREATED: "clock",
        ActivityType.APPROVAL_SUBMITTED: "clock",
        ActivityType.APPROVAL_APPROVED: "check",
        ActivityType.APPROVAL_RETURNED: "return",
        ActivityType.APPROVAL_REJECTED: "x",
        ActivityType.APPROVAL_CANCELLED: "ban",
    }

    def get_events(
        self,
        project_id: int,
        records: list[dict[str, Any]] | None = None,
    ) -> list[TimelineEntry]:
        rows = (
            records
            if records is not None
            else ActivityRepository.list_project_activities(project_id)
        )
        return [self._entry(project_id, row) for row in rows]

    @classmethod
    def _entry(cls, project_id: int, activity: dict[str, Any]) -> TimelineEntry:
        details = activity.get("details") or ""
        visit_match = re.search(r"\[visita:(\d+)\]", details)
        approval_match = re.search(r"AP-(\d{6})", details)
        deduplication_key = None
        if visit_match:
            deduplication_key = f"visit:{int(visit_match.group(1))}"
        approval_event = cls._APPROVAL_EVENTS.get(activity.get("activity_type"))
        if approval_match and approval_event:
            deduplication_key = (
                f"approval:{int(approval_match.group(1))}:{approval_event}"
            )
        return TimelineEntry(
            id=f"activity-{activity['id']}",
            event_type=cls.event_type,
            icon="calendar-check",
            color="neutral",
            title=activity["title"],
            description=re.sub(r"\n?\[visita:\d+\]", "", details),
            source="Actividad",
            reference_id=activity["id"],
            date=activity.get("occurred_at") or activity.get("created_at"),
            user=activity.get("created_by") or "Sistema",
            endpoint="workspace.project_detail",
            endpoint_values={
                "project_id": project_id,
                "_anchor": f"timeline-entry-activity-{activity['id']}",
            },
            category=(
                TimelineCategory.COMMERCIAL
                if ActivityType.is_manual_type(activity.get("activity_type"))
                else TimelineCategory.SYSTEM
            ),
            deduplication_key=deduplication_key,
        )

    @classmethod
    def present(cls, activity: dict[str, Any]) -> dict[str, Any]:
        """Preserve the pre-provider activity presentation contract."""
        match = re.search(r"AP-(\d{6})", activity.get("details") or "")
        visit_match = re.search(
            r"\[visita:(\d+)\]", activity.get("details") or ""
        )
        return {
            **activity,
            "details": re.sub(
                r"\n?\[visita:\d+\]", "", activity.get("details") or ""
            ),
            "timeline_icon": cls._LEGACY_ICONS.get(
                activity.get("activity_type"), ""
            ),
            "approval_id": int(match.group(1)) if match else None,
            "approval_number": match.group(0) if match else None,
            "visit_id": int(visit_match.group(1)) if visit_match else None,
        }
