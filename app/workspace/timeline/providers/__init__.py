from app.workspace.timeline.providers.activity_provider import (
    ActivityTimelineProvider,
)
from app.workspace.timeline.providers.approval_provider import (
    ApprovalTimelineProvider,
)
from app.workspace.timeline.providers.file_provider import FileTimelineProvider
from app.workspace.timeline.providers.quote_provider import QuoteTimelineProvider
from app.workspace.timeline.providers.visit_provider import VisitTimelineProvider


TIMELINE_PROVIDERS = (
    ActivityTimelineProvider(),
    VisitTimelineProvider(),
    QuoteTimelineProvider(),
    ApprovalTimelineProvider(),
    FileTimelineProvider(),
)

__all__ = [
    "ActivityTimelineProvider",
    "ApprovalTimelineProvider",
    "FileTimelineProvider",
    "QuoteTimelineProvider",
    "TIMELINE_PROVIDERS",
    "VisitTimelineProvider",
]
