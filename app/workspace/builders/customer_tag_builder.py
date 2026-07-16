from typing import Any


class CustomerTagBuilder:

    @staticmethod
    def build(
        *,
        customer: dict[str, Any],
        agreement: dict[str, Any] | None,
        pipeline: dict[str, Any],
    ) -> list[dict]:

        tags = []

        if agreement:
            tags.append(
                {
                    "label": agreement["supplier"],
                    "color": "blue",
                }
            )

        if pipeline.get("active_project_count", 0):
            tags.append(
                {
                    "label": "Activo",
                    "color": "green",
                }
            )

        if customer.get("industry"):
            tags.append(
                {
                    "label": customer["industry"],
                    "color": "secondary",
                }
            )

        return tags