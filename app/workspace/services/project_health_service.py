from datetime import date, datetime
from typing import Any


class ProjectHealthService:

    FILTER_OPTIONS = (
        ("active", "Activa"),
        ("at_risk", "En riesgo"),
        ("waiting_customer", "Esperando cliente"),
        ("needs_followup", "Requiere seguimiento"),
        ("won", "Ganada"),
        ("lost", "Perdida"),
        ("cancelled", "Cancelada"),
    )

    @staticmethod
    def filter_options() -> list[dict[str, str]]:
        return [
            {"value": value, "label": label}
            for value, label in ProjectHealthService.FILTER_OPTIONS
        ]

    @staticmethod
    def calculate(
        workspace: dict[str, Any],
    ) -> dict[str, str]:
        project = workspace["project"]
        followups = workspace.get("followups", [])
        activities = workspace.get("activities", [])
        today = date.today()

        has_overdue_followup = any(
            ProjectHealthService._is_overdue(
                followup=followup,
                today=today,
            )
            for followup in followups
        )
        last_activity_at = ProjectHealthService._get_last_activity_at(
            activities
        )

        return ProjectHealthService.calculate_summary(
            project_status=project["status"],
            has_overdue_followup=has_overdue_followup,
            last_activity_at=last_activity_at,
        )

    @staticmethod
    def calculate_summary(
        *,
        project_status: str,
        has_overdue_followup: bool,
        last_activity_at: datetime | None,
    ) -> dict[str, str]:

        if project_status == "won":
            return {
                "key": "won",
                "badge": "blue",
                "label": "Ganado",
            }

        if project_status == "lost":
            return {
                "key": "lost",
                "badge": "dark",
                "label": "Perdido",
            }

        if project_status == "cancelled":
            return {
                "key": "cancelled",
                "badge": "secondary",
                "label": "Cancelado",
            }

        if has_overdue_followup:
            return {
                "key": "at_risk",
                "badge": "danger",
                "label": "Seguimiento vencido",
            }

        if project_status == "waiting_customer":
            return {
                "key": "waiting_customer",
                "badge": "warning",
                "label": "Esperando cliente",
            }

        if last_activity_at is not None:
            days_since_activity = (
                datetime.now() - last_activity_at
            ).days

            if days_since_activity <= 7:
                return {
                    "key": "active",
                    "badge": "success",
                    "label": "Activo",
                }

            if days_since_activity >= 21:
                return {
                    "key": "at_risk",
                    "badge": "danger",
                    "label": "Sin actividad reciente",
                }

        return {
            "key": "needs_followup",
            "badge": "secondary",
            "label": "Requiere seguimiento",
        }

    @staticmethod
    def _is_overdue(
        *,
        followup: dict[str, Any],
        today: date,
    ) -> bool:
        if followup.get("status") != "pending":
            return False

        due_date_text = followup.get("due_date")

        if not due_date_text:
            return False

        try:
            due_date = datetime.strptime(
                due_date_text,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            return False

        return due_date < today

    @staticmethod
    def _get_last_activity_at(
        activities: list[dict[str, Any]],
    ) -> datetime | None:
        if not activities:
            return None

        activity = activities[0]

        timestamp = (
            activity.get("occurred_at")
            or activity.get("created_at")
        )

        if not timestamp:
            return None

        return ProjectHealthService.parse_activity_timestamp(timestamp)

    @staticmethod
    def parse_activity_timestamp(
        timestamp: str | None,
    ) -> datetime | None:
        if not timestamp:
            return None

        try:
            return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
