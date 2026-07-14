from datetime import date, datetime
from typing import Any


class ProjectHealthService:

    @staticmethod
    def calculate(
        workspace: dict[str, Any],
    ) -> dict[str, str]:
        project = workspace["project"]
        followups = workspace.get("followups", [])
        activities = workspace.get("activities", [])

        project_status = project["status"]
        today = date.today()

        if project_status == "won":
            return {
                "badge": "blue",
                "label": "Ganado",
            }

        if project_status == "lost":
            return {
                "badge": "dark",
                "label": "Perdido",
            }

        has_overdue_followup = any(
            ProjectHealthService._is_overdue(
                followup=followup,
                today=today,
            )
            for followup in followups
        )

        if has_overdue_followup:
            return {
                "badge": "danger",
                "label": "Seguimiento vencido",
            }

        if project_status == "waiting_customer":
            return {
                "badge": "warning",
                "label": "Esperando cliente",
            }

        last_activity_at = (
            ProjectHealthService._get_last_activity_at(
                activities
            )
        )

        if last_activity_at is not None:
            days_since_activity = (
                datetime.now() - last_activity_at
            ).days

            if days_since_activity <= 7:
                return {
                    "badge": "success",
                    "label": "Activo",
                }

            if days_since_activity >= 21:
                return {
                    "badge": "danger",
                    "label": "Sin actividad reciente",
                }

        return {
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

        try:
            return datetime.strptime(
                timestamp,
                "%Y-%m-%d %H:%M:%S",
            )
        except ValueError:
            return None