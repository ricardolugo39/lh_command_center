from datetime import date, datetime
from typing import Any

from app.workspace.constants.project_status import is_open


class CommercialPriorityBuilder:

    @staticmethod
    def build(
        *,
        projects: list[dict[str, Any]],
        pipeline: dict[str, Any],
        agreement: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        priorities: list[dict[str, Any]] = []

        active_projects = [
            project
            for project in projects
            if is_open(project.get("status"))
        ]

        blocked_projects = [
            project
            for project in active_projects
            if project.get("current_blocker")
        ]

        if agreement is None:
            priorities.append(
                {
                    "severity": "danger",
                    "title": "Formalizar convenio comercial",
                    "description": (
                        "El cliente no tiene un convenio registrado."
                    ),
                }
            )
        else:
            days_until_end = (
                CommercialPriorityBuilder._days_until(
                    agreement.get("end_date")
                )
            )

            if (
                days_until_end is not None
                and 0 <= days_until_end <= 90
            ):
                priorities.append(
                    {
                        "severity": "warning",
                        "title": "Iniciar renovación del convenio",
                        "description": (
                            f"El convenio vence en "
                            f"{days_until_end} días."
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
                        "title": "Regularizar convenio vencido",
                        "description": (
                            "El convenio registrado ya venció."
                        ),
                    }
                )

        if active_projects:
            priorities.append(
                {
                    "severity": "info",
                    "title": (
                        f"Dar seguimiento a "
                        f"{len(active_projects)} "
                        f"{'proyecto activo' if len(active_projects) == 1 else 'proyectos activos'}"
                    ),
                    "description": (
                        "Revisar ejecución y próximas acciones."
                    ),
                }
            )
        else:
            priorities.append(
                {
                    "severity": "secondary",
                    "title": "Generar nuevas oportunidades comerciales",
                    "description": (
                        "El cliente no tiene proyectos activos."
                    ),
                }
            )

        if blocked_projects:
            priorities.append(
                {
                    "severity": "warning",
                    "title": (
                        f"Resolver "
                        f"{len(blocked_projects)} "
                        f"{'proyecto bloqueado' if len(blocked_projects) == 1 else 'proyectos bloqueados'}"
                    ),
                    "description": (
                        "Revisar los bloqueos que afectan el avance."
                    ),
                }
            )

        if agreement and not active_projects:
            priorities.append(
                {
                    "severity": "warning",
                    "title": (
                        "Aprovechar el convenio para generar proyectos"
                    ),
                    "description": (
                        "El cliente tiene convenio pero no oportunidades activas."
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

        return (target_date - date.today()).days
