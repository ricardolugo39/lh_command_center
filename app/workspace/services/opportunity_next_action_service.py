from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.workspace.constants.project_status import (
    PIPELINE_STATUS_ORDER,
    ProjectStatus,
    is_open,
)
from app.workspace.timeline.entry import TimelineCategory, TimelineEntry


PRIORITY_ORDER = {
    "Critical": 0,
    "High": 1,
    "Medium": 2,
    "Low": 3,
}


@dataclass(frozen=True)
class NextAction:
    title: str
    description: str
    priority: str
    category: str
    action_type: str
    related_entity: str
    related_entity_id: int
    due_date: str | None = None

    @property
    def navigation(self) -> dict[str, Any]:
        project_id = self.related_entity_id
        destinations = {
            "schedule_followup": (
                "workspace.project_detail",
                {"project_id": project_id, "_anchor": "schedule-followup"},
            ),
            "review_pending_approvals": (
                "workspace.commercial_approval_list",
                {"project_id": project_id},
            ),
            "resolve_blocker": (
                "workspace.project_detail",
                {"project_id": project_id, "_anchor": "blocker-form"},
            ),
            "contact_customer": (
                "workspace.project_detail",
                {"project_id": project_id, "_anchor": "register-activity"},
            ),
            "create_quote": (
                "workspace.edit_project",
                {"project_id": project_id, "_anchor": "quote-section"},
            ),
            "complete_commercial_value": (
                "workspace.commercial_approval_new",
                {"project_id": project_id},
            ),
        }
        endpoint, values = destinations[self.action_type]
        return {"endpoint": endpoint, "values": values}

    @property
    def priority_label(self) -> str:
        return {
            "Critical": "Crítica",
            "High": "Alta",
            "Medium": "Media",
            "Low": "Baja",
        }[self.priority]

    @property
    def priority_tone(self) -> str:
        return {
            "Critical": "danger",
            "High": "warning",
            "Medium": "blue",
            "Low": "secondary",
        }[self.priority]


class OpportunityNextActionService:
    """Evaluate deterministic, read-only Opportunity recommendations."""

    @classmethod
    def get_actions(
        cls,
        *,
        opportunity: dict[str, Any],
        followups: list[dict[str, Any]],
        pending_approval_count: int,
        timeline: list[TimelineEntry],
        quotes: list[dict[str, Any]],
        today: date | None = None,
    ) -> tuple[NextAction, ...]:
        if not is_open(opportunity.get("status")):
            return ()

        today = today or date.today()
        project_id = int(opportunity["id"])
        actions: list[NextAction] = []
        has_pending_followup = any(
            item.get("status") == "pending" for item in followups
        )

        if (
            opportunity.get("status") == ProjectStatus.WAITING_CUSTOMER
            and not has_pending_followup
        ):
            actions.append(cls._action(
                project_id,
                title="Programar seguimiento",
                description="No hay un seguimiento programado para esta oportunidad.",
                priority="High",
                category="Seguimiento",
                action_type="schedule_followup",
            ))

        if pending_approval_count > 0:
            actions.append(cls._action(
                project_id,
                title="Revisar aprobaciones pendientes",
                description="Hay solicitudes comerciales pendientes de decisión.",
                priority="High",
                category="Aprobación",
                action_type="review_pending_approvals",
            ))

        if str(opportunity.get("current_blocker") or "").strip():
            actions.append(cls._action(
                project_id,
                title="Resolver bloqueo comercial",
                description=str(opportunity["current_blocker"]).strip(),
                priority="Critical",
                category="Bloqueo",
                action_type="resolve_blocker",
            ))

        latest_commercial = next(
            (
                entry for entry in timeline
                if entry.category is TimelineCategory.COMMERCIAL
                and entry.date
            ),
            None,
        )
        days_since_activity = cls._days_since(
            latest_commercial.date if latest_commercial else None,
            today,
        )
        if days_since_activity is not None and days_since_activity > 15:
            actions.append(cls._action(
                project_id,
                title="Contactar al cliente",
                description=(
                    f"La última actividad comercial fue hace "
                    f"{days_since_activity} días."
                ),
                priority="High",
                category="Actividad comercial",
                action_type="contact_customer",
            ))

        if not quotes and cls._is_at_or_after_quotation(
            opportunity.get("status")
        ):
            actions.append(cls._action(
                project_id,
                title="Crear cotización",
                description="La etapa actual requiere una cotización registrada.",
                priority="High",
                category="Cotización",
                action_type="create_quote",
            ))

        if opportunity.get("commercial_amount") in (None, ""):
            actions.append(cls._action(
                project_id,
                title="Completar proceso de valor comercial",
                description="La oportunidad no tiene un monto comercial aprobado.",
                priority="Medium",
                category="Valor comercial",
                action_type="complete_commercial_value",
            ))

        unique = {action.action_type: action for action in actions}
        return tuple(sorted(
            unique.values(),
            key=lambda action: PRIORITY_ORDER[action.priority],
        ))

    @staticmethod
    def _action(
        project_id: int,
        *,
        title: str,
        description: str,
        priority: str,
        category: str,
        action_type: str,
    ) -> NextAction:
        return NextAction(
            title=title,
            description=description,
            priority=priority,
            category=category,
            action_type=action_type,
            related_entity="opportunity",
            related_entity_id=project_id,
        )

    @staticmethod
    def _days_since(value: str | None, today: date) -> int | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(
                str(value).strip().replace("Z", "+00:00")
            ).date()
        except ValueError:
            return None
        return max((today - parsed).days, 0)

    @staticmethod
    def _is_at_or_after_quotation(status: str | None) -> bool:
        if status not in PIPELINE_STATUS_ORDER:
            return False
        return PIPELINE_STATUS_ORDER.index(status) >= (
            PIPELINE_STATUS_ORDER.index(ProjectStatus.QUOTING)
        )
