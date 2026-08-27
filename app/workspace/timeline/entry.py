from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TimelineEventType(Enum):
    ACTIVITY = "activity"
    VISIT = "visit"
    QUOTE = "quote"
    APPROVAL = "approval"
    FILE = "file"


class TimelineCategory(Enum):
    COMMERCIAL = "commercial"
    SYSTEM = "system"


@dataclass(frozen=True)
class TimelineEntry:
    id: str
    event_type: TimelineEventType
    icon: str
    color: str
    title: str
    description: str
    source: str
    reference_id: int
    date: str | None
    user: str
    endpoint: str
    endpoint_values: dict[str, Any] = field(default_factory=dict)
    category: TimelineCategory = TimelineCategory.SYSTEM
    deduplication_key: str | None = None
    deduplication_priority: int = 0

    @property
    def type(self) -> str:
        """Backward-compatible value used by Sprint 2.0 callers."""
        return self.event_type.value
