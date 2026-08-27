from decimal import Decimal
from typing import Any

from app.workspace.repositories.commercial_approval_repository import (
    CommercialApprovalRepository,
)
from app.workspace.timeline.entry import (
    TimelineCategory,
    TimelineEntry,
    TimelineEventType,
)
from app.workspace.timeline.providers.base import TimelineProvider


class ApprovalTimelineProvider(TimelineProvider):
    event_type = TimelineEventType.APPROVAL
    TITLES = {
        "created": "Solicitud de aprobación comercial creada",
        "submitted": "Aprobación comercial enviada",
        "approved": "Descuento comercial aprobado",
        "returned": "Aprobación comercial devuelta",
        "rejected": "Aprobación comercial rechazada",
        "cancelled": "Solicitud de aprobación cancelada",
        "expired": "Aprobación comercial vencida",
    }
    def get_events(
        self,
        project_id: int,
        records: list[dict[str, Any]] | None = None,
    ) -> list[TimelineEntry]:
        rows = (
            records
            if records is not None
            else CommercialApprovalRepository.list_project_timeline_events(
                project_id
            )
        )
        return [self._entry(row) for row in rows]

    @classmethod
    def _entry(cls, event: dict[str, Any]) -> TimelineEntry:
        approval_id = int(event["approval_id"])
        number = f"AP-{approval_id:06d}"
        details = [number]
        if event.get("requested_discount") is not None:
            details.append(
                "Descuento solicitado: "
                f"{cls._percent(event['requested_discount'])}"
            )
        if event.get("comments"):
            details.append(event["comments"])
        return TimelineEntry(
            id=f"approval-{event['id']}",
            event_type=cls.event_type,
            icon="check-circle",
            color="neutral",
            title=cls.TITLES[event["event_type"]],
            description=" · ".join(details),
            source="Aprobación",
            reference_id=approval_id,
            date=event.get("created_at"),
            user=event.get("actor") or "Sistema",
            endpoint="workspace.commercial_approval_detail",
            endpoint_values={"approval_id": approval_id},
            category=TimelineCategory.SYSTEM,
            deduplication_key=(
                f"approval:{approval_id}:{event['event_type']}"
            ),
            deduplication_priority=10,
        )

    @staticmethod
    def _percent(value) -> str:
        return (
            f"{Decimal(str(value or 0)).quantize(Decimal('0.01'))}%"
            .replace(".", ",")
        )
