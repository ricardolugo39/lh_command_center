from typing import Any


class CustomerKPIBuilder:

    @staticmethod
    def build(
        *,
        sales: dict[str, Any],
        pipeline: dict[str, Any],
        display_pipeline: str,
    ) -> dict[str, Any]:
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
            "relationship_score": None,
        }