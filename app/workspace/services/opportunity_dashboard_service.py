from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.workspace.constants.project_status import get_status_label
from app.workspace.constants.quote_status import is_open_quote_status
from app.workspace.repositories.commercial_approval_repository import (
    CommercialApprovalRepository,
)
from app.workspace.services.opportunity_list_service import OpportunityListService
from app.workspace.timeline.entry import TimelineEntry, TimelineEventType


@dataclass(frozen=True)
class OpportunityDashboard:
    opportunity: dict[str, Any]
    health: dict[str, Any]
    commercial_value: dict[str, str | None]
    summary_metrics: tuple[dict[str, Any], ...]
    latest_events: tuple[TimelineEntry, ...]
    counts: dict[str, int]
    derived_dates: dict[str, Any]


class OpportunityDashboardService:
    """Build the read-only command-center summary from loaded Opportunity data."""

    @classmethod
    def get_dashboard(
        cls,
        *,
        opportunity: dict[str, Any],
        customer: dict[str, Any],
        timeline: list[TimelineEntry],
        followups: list[dict[str, Any]],
        quotes: list[dict[str, Any]],
        files: list[dict[str, Any]],
        approval: dict[str, Any] | None,
        crm_potential_value: Any = None,
        today: date | None = None,
    ) -> OpportunityDashboard:
        today = today or date.today()
        latest_activity = cls._latest(
            timeline,
            {TimelineEventType.ACTIVITY, TimelineEventType.VISIT},
        )
        latest_visit = cls._latest(timeline, {TimelineEventType.VISIT})
        latest_quote = cls._latest(timeline, {TimelineEventType.QUOTE})
        latest_movement = timeline[0] if timeline else None

        pending_followups = [
            item for item in followups if item.get("status") == "pending"
        ]
        overdue_followups = [
            item
            for item in pending_followups
            if cls._is_overdue(item.get("due_date"), today)
        ]
        open_quotes = [
            quote
            for quote in quotes
            if is_open_quote_status(quote.get("quote_status"))
        ]
        approval_metrics = CommercialApprovalRepository.get_metrics(
            opportunity["id"]
        )
        pending_approvals = int(approval_metrics.get("pending") or 0)

        days_since_activity = cls._days_since(
            latest_activity.date if latest_activity else None,
            today,
        )
        days_since_visit = cls._days_since(
            latest_visit.date if latest_visit else None,
            today,
        )
        crm_source = opportunity.get("crm_source") or {}
        opened_at = crm_source.get("date") or opportunity.get("created_at")
        opened_date = cls._parse_date(opened_at)
        closed_date = cls._parse_date(opportunity.get("closed_at"))
        age_end = closed_date or today
        days_open = max((age_end - opened_date).days, 0) if opened_date else None
        health = cls.calculate_health(
            days_since_activity=days_since_activity,
            has_overdue_followups=bool(overdue_followups),
        )
        counts = {
            "pending_approvals": pending_approvals,
            "open_quotes": len(open_quotes),
            "open_followups": len(pending_followups),
            "overdue_followups": len(overdue_followups),
            "files": len(files),
        }
        derived_dates = {
            "last_activity": latest_activity.date if latest_activity else None,
            "last_visit": latest_visit.date if latest_visit else None,
            "last_quote": latest_quote.date if latest_quote else None,
            "latest_movement": (
                latest_movement.date if latest_movement else None
            ),
            "days_since_activity": days_since_activity,
            "days_since_visit": days_since_visit,
            "next_followup": (
                pending_followups[0].get("due_date")
                if pending_followups
                else None
            ),
            "opened_at": opened_date.isoformat() if opened_date else None,
            "days_open": days_open,
            "open_age_label": cls._open_age_label(
                days_open, is_closed=closed_date is not None
            ),
        }
        status_label = get_status_label(opportunity.get("status"))
        commercial_value = OpportunityListService.present_commercial_value(
            opportunity,
            quotes[0] if quotes else None,
            crm_potential_value,
        )
        probability = approval.get("probability") if approval else None

        metrics = [
            cls._metric("Estado actual", status_label, "Etapa comercial vigente"),
            cls._metric(
                "Salud",
                health["label"],
                health["detail"],
                tone=health["tone"],
            ),
            cls._metric(
                "Bloqueo actual",
                opportunity.get("current_blocker") or "Sin bloqueo",
                "Restricción comercial vigente",
                tone="warning" if opportunity.get("current_blocker") else "neutral",
            ),
            cls._metric(
                "Responsable",
                opportunity.get("sales_rep") or "Sin asignar",
                "Propietario comercial",
            ),
            cls._metric(
                "Última actividad",
                cls._event_date(latest_activity),
                cls._days_label(days_since_activity),
            ),
        ]
        if probability not in (None, ""):
            metrics.append(
                cls._metric(
                    "Probabilidad",
                    f"{probability}%",
                    "Último dato disponible",
                )
            )
        return OpportunityDashboard(
            opportunity=opportunity,
            health=health,
            commercial_value=commercial_value,
            summary_metrics=tuple(metrics),
            latest_events=tuple(timeline[:3]),
            counts=counts,
            derived_dates=derived_dates,
        )

    @staticmethod
    def calculate_health(
        *, days_since_activity: int | None, has_overdue_followups: bool
    ) -> dict[str, str]:
        if days_since_activity is None or days_since_activity >= 30:
            return {
                "key": "red",
                "tone": "danger",
                "label": "En riesgo",
                "detail": "Sin actividad en 30 días o más",
            }
        if days_since_activity >= 15:
            return {
                "key": "yellow",
                "tone": "warning",
                "label": "Atención",
                "detail": "Sin actividad en 15 días o más",
            }
        if has_overdue_followups:
            return {
                "key": "yellow",
                "tone": "warning",
                "label": "Atención",
                "detail": "Tiene follow-ups vencidos",
            }
        return {
            "key": "green",
            "tone": "success",
            "label": "Saludable",
            "detail": "Actividad reciente y sin follow-ups vencidos",
        }

    @staticmethod
    def _latest(
        timeline: list[TimelineEntry], event_types: set[TimelineEventType]
    ) -> TimelineEntry | None:
        return next(
            (item for item in timeline if item.event_type in event_types),
            None,
        )

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(
                str(value).strip().replace("Z", "+00:00")
            ).date()
        except ValueError:
            return None

    @classmethod
    def _days_since(cls, value: str | None, today: date) -> int | None:
        parsed = cls._parse_date(value)
        return max((today - parsed).days, 0) if parsed else None

    @classmethod
    def _is_overdue(cls, value: str | None, today: date) -> bool:
        parsed = cls._parse_date(value)
        return parsed < today if parsed else False

    @staticmethod
    def _days_label(value: int | None) -> str:
        if value is None:
            return "Sin registro"
        if value == 0:
            return "Hoy"
        return f"Hace {value} días"

    @staticmethod
    def _open_age_label(value: int | None, *, is_closed: bool) -> str:
        if value is None:
            return "Sin fecha de apertura"
        unit = "día" if value == 1 else "días"
        return f"Duró {value} {unit}" if is_closed else f"Abierta hace {value} {unit}"

    @staticmethod
    def _event_date(event: TimelineEntry | None) -> str:
        return event.date if event and event.date else "Sin registro"

    @staticmethod
    def _metric(
        label: str,
        value: str,
        detail: str,
        *,
        tone: str = "neutral",
    ) -> dict[str, str]:
        return {"label": label, "value": value, "detail": detail, "tone": tone}
