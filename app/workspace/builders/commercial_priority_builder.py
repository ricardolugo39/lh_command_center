from datetime import date, datetime
from typing import Any


class CommercialPriorityBuilder:

    @staticmethod
    def build(
        *,
        projects: list[dict[str, Any]],
        pipeline: dict[str, Any],
        agreement: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        priorities: list[dict[str, Any]] = []

        active_project_count = int(
            pipeline.get(
                "active_project_count",
                0,
            )
            or 0
        )

        if agreement:
            days_until_end = (
                CommercialPriorityBuilder
                ._days_until(
                    agreement.get("end_date")
                )
            )

            if (
                days_until_end is not None
                and 0 <= days_until_end <= 90
            ):
                priorities.append(
                    {
                        "severity": "danger",
                        "title": (
                            "Convenio próximo a vencer"
                        ),
                        "description": (
                            f"El convenio vence en "
                            f"{days_until_end} días. "
                            "Iniciar preparación de renovación."
                        ),
                    }
                )

            elif (
                days_until_end is not None
                and days_until_end < 0
            ):
                priorities.append(
                    {
                        "severity": "danger",
                        "title": "Convenio vencido",
                        "description": (
                            "Revisar renovación o cierre "
                            "del convenio."
                        ),
                    }
                )

        else:
            priorities.append(
                {
                    "severity": "warning",
                    "title": "Sin convenio comercial",
                    "description": (
                        "El cliente no tiene un convenio "
                        "registrado."
                    ),
                }
            )

        if active_project_count > 0:
            priorities.append(
                {
                    "severity": "info",
                    "title": (
                        f"{active_project_count} "
                        "proyecto"
                        if active_project_count == 1
                        else (
                            f"{active_project_count} "
                            "proyectos activos"
                        )
                    ),
                    "description": (
                        "Revisar ejecución, bloqueos "
                        "y próximas acciones."
                    ),
                }
            )

        else:
            priorities.append(
                {
                    "severity": "secondary",
                    "title": "Sin oportunidades activas",
                    "description": (
                        "El cliente no tiene proyectos "
                        "comerciales activos."
                    ),
                }
            )

        blocked_projects = [
            project
            for project in projects
            if (
                project.get("current_blocker")
                and project.get("status")
                not in {"won", "lost"}
            )
        ]

        if blocked_projects:
            priorities.append(
                {
                    "severity": "warning",
                    "title": (
                        f"{len(blocked_projects)} "
                        "proyecto bloqueado"
                        if len(blocked_projects) == 1
                        else (
                            f"{len(blocked_projects)} "
                            "proyectos bloqueados"
                        )
                    ),
                    "description": (
                        "Revisar los bloqueos que están "
                        "afectando el avance comercial."
                    ),
                }
            )

        return priorities

    @staticmethod
    def _days_until(
        value: str | None,
    ) -> int | None:
        if not value:
            return None

        try:
            target_date = datetime.strptime(
                value,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            return None

        return (
            target_date - date.today()
        ).days