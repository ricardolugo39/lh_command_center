from datetime import datetime
from typing import Any

from app.workspace.timeline.entry import TimelineEntry, TimelineEventType
from app.workspace.timeline.providers import TIMELINE_PROVIDERS
from app.workspace.timeline.providers.activity_provider import (
    ActivityTimelineProvider,
)
from app.workspace.timeline.publisher import OpportunityTimelinePublisher


class OpportunityTimelineService:
    """Orchestrate registered providers into one canonical timeline."""

    providers = TIMELINE_PROVIDERS

    @classmethod
    def get_timeline(
        cls,
        project_id: int,
        *,
        activities: list[dict[str, Any]] | None = None,
        quotes: list[dict[str, Any]] | None = None,
        files: list[dict[str, Any]] | None = None,
    ) -> list[TimelineEntry]:
        """Preserve the Sprint 2.0 API while delegating source work."""
        preloaded = {
            TimelineEventType.ACTIVITY: activities,
            TimelineEventType.QUOTE: quotes,
            TimelineEventType.FILE: files,
        }
        events = []
        for provider in cls.providers:
            events.extend(
                provider.get_events(
                    project_id,
                    records=preloaded.get(provider.event_type),
                )
            )
        return cls._sort_events(cls._deduplicate(events))

    @staticmethod
    def _deduplicate(events: list[TimelineEntry]) -> list[TimelineEntry]:
        canonical: dict[str, TimelineEntry] = {}
        for event in events:
            key = event.deduplication_key or event.id
            existing = canonical.get(key)
            if (
                existing is None
                or event.deduplication_priority
                > existing.deduplication_priority
            ):
                canonical[key] = event
        return list(canonical.values())

    @classmethod
    def _sort_events(
        cls, events: list[TimelineEntry]
    ) -> list[TimelineEntry]:
        return sorted(
            events,
            key=lambda event: (cls._sort_date(event.date), event.id),
            reverse=True,
        )

    @staticmethod
    def _sort_date(value: str | None) -> datetime:
        if not value:
            return datetime.min
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            return parsed
        except ValueError:
            return datetime.min

    @staticmethod
    def publish_approval_event(**kwargs) -> int:
        return OpportunityTimelinePublisher.publish_approval_event(**kwargs)

    @staticmethod
    def publish_visit_event(**kwargs) -> int:
        return OpportunityTimelinePublisher.publish_visit_event(**kwargs)

    @staticmethod
    def present(activity: dict[str, Any]) -> dict[str, Any]:
        return ActivityTimelineProvider.present(activity)
