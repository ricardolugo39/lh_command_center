from abc import ABC, abstractmethod
from typing import Any

from app.workspace.timeline.entry import TimelineEntry, TimelineEventType


class TimelineProvider(ABC):
    event_type: TimelineEventType

    @abstractmethod
    def get_events(
        self,
        project_id: int,
        records: list[dict[str, Any]] | None = None,
    ) -> list[TimelineEntry]:
        """Query one source and normalize its records."""
