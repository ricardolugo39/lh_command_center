class CustomerInsightBuilder:

    @staticmethod
    def build(
        *,
        sales: dict,
        pipeline: dict,
    ) -> dict:

        return {

            "sales_current_year": (
                sales.get(
                    "display_current_year"
                )
            ),

            "sales_last_12_months": (
                sales.get(
                    "display_last_12_months"
                )
            ),

            "last_purchase": (
                sales.get(
                    "last_purchase_date"
                )
            ),

            "pipeline": pipeline.get(
                "open_pipeline_cop",
                0,
            ),

            "active_projects": pipeline.get(
                "active_project_count",
                0,
            ),
        }