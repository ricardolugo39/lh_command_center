from typing import Any

from app.workspace.services.quote_service import QuoteService
from app.workspace.timeline.entry import (
    TimelineCategory,
    TimelineEntry,
    TimelineEventType,
)
from app.workspace.timeline.providers.base import TimelineProvider


class QuoteTimelineProvider(TimelineProvider):
    event_type = TimelineEventType.QUOTE

    def get_events(
        self,
        project_id: int,
        records: list[dict[str, Any]] | None = None,
    ) -> list[TimelineEntry]:
        rows = (
            records
            if records is not None
            else QuoteService.list_project_quotes(project_id)
        )
        return [self._entry(row) for row in rows]

    @classmethod
    def _entry(cls, quote: dict[str, Any]) -> TimelineEntry:
        details = [quote.get("display_amount") or "Sin valor registrado"]
        if quote.get("quote_status"):
            details.append(f"Estado: {quote['quote_status']}")
        return TimelineEntry(
            id=f"quote-{quote['id']}",
            event_type=cls.event_type,
            icon="file-text",
            color="neutral",
            title=f"Cotización {quote['display_quote_number']} creada",
            description=" · ".join(details),
            source="Cotización",
            reference_id=quote["id"],
            date=quote.get("quote_date") or quote.get("created_at"),
            user=quote.get("erp_user") or "Sistema",
            endpoint="workspace.edit_quote",
            endpoint_values={"quote_id": quote["id"]},
            category=TimelineCategory.COMMERCIAL,
        )
