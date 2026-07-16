from typing import Any


class CustomerKPIBuilder:

    @staticmethod
    def build(
        *,
        sales: dict[str, Any],
        pipeline: dict[str, Any],
        display_pipeline: str,
        agreement: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if agreement:
            agreement_status = (
                agreement.get("status")
                or "active"
            )

            agreement_label = {
                "draft": "Borrador",
                "active": "Activo",
                "renewal": "Renovación",
                "expired": "Vencido",
                "closed": "Cerrado",
            }.get(
                agreement_status,
                agreement_status,
            )

            agreement_badge = {
                "draft": "secondary",
                "active": "green",
                "renewal": "yellow",
                "expired": "red",
                "closed": "secondary",
            }.get(
                agreement_status,
                "secondary",
            )
        else:
            agreement_label = "Sin convenio"
            agreement_badge = "red"

        return {
            "sales_ytd": (
                sales.get("display_current_year")
                or "COP 0"
            ),
            "pipeline": (
                display_pipeline
                or "COP 0"
            ),
            "active_projects": (
                pipeline.get(
                    "active_project_count",
                    0,
                )
            ),
            "agreement_label": agreement_label,
            "agreement_badge": agreement_badge,
        }