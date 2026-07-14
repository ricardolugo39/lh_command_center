from datetime import date, datetime, timedelta
from typing import Any

from app.workspace.repositories.workspace_dashboard_repository import (
    WorkspaceDashboardRepository,
)


class WorkspaceDashboardService:

    UPCOMING_DAYS = 7

    @staticmethod
    def get_dashboard() -> dict[str, Any]:
        followups = (
            WorkspaceDashboardRepository
            .list_pending_followups()
        )

        today = date.today()
        upcoming_limit = today + timedelta(
            days=WorkspaceDashboardService.UPCOMING_DAYS
        )

        overdue_followups = []
        today_followups = []
        upcoming_followups = []

        for followup in followups:
            due_date = (
                WorkspaceDashboardService
                ._parse_date(
                    followup.get("due_date")
                )
            )

            if due_date is None:
                continue

            enriched_followup = {
                **followup,
                "days_from_today": (
                    due_date - today
                ).days,
                "display_due_date": (
                    WorkspaceDashboardService
                    ._format_date(due_date)
                ),
            }

            if due_date < today:
                overdue_followups.append(
                    enriched_followup
                )

            elif due_date == today:
                today_followups.append(
                    enriched_followup
                )

            elif due_date <= upcoming_limit:
                upcoming_followups.append(
                    enriched_followup
                )

        recent_projects = (
            WorkspaceDashboardRepository
            .list_recent_projects(limit=5)
        )

        return {
            "overdue_followups": overdue_followups,
            "today_followups": today_followups,
            "upcoming_followups": upcoming_followups,
            "recent_projects": recent_projects,
            "summary": {
                "overdue_count": len(
                    overdue_followups
                ),
                "today_count": len(
                    today_followups
                ),
                "upcoming_count": len(
                    upcoming_followups
                ),
            },
        }

    @staticmethod
    def _parse_date(
        value: str | None,
    ) -> date | None:
        if not value:
            return None

        try:
            return datetime.strptime(
                value,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            return None

    @staticmethod
    def _format_date(
        value: date,
    ) -> str:
        months = {
            1: "ene",
            2: "feb",
            3: "mar",
            4: "abr",
            5: "may",
            6: "jun",
            7: "jul",
            8: "ago",
            9: "sep",
            10: "oct",
            11: "nov",
            12: "dic",
        }

        return (
            f"{value.day} "
            f"{months[value.month]} "
            f"{value.year}"
        )