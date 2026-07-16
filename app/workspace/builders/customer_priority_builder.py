class CustomerPriorityBuilder:

    @staticmethod
    def build(
        *,
        customer: dict,
        projects: list,
        pipeline: dict,
        sales: dict,
    ) -> list[dict]:

        priorities = []

        #
        # Rule 1
        #

        if len(projects) == 0:

            priorities.append(
                {
                    "severity": "warning",
                    "title": "No active projects",
                    "description": (
                        "Create a commercial opportunity."
                    ),
                }
            )

        #
        # Rule 2
        #

        if (
            pipeline.get(
                "open_pipeline_cop",
                0,
            )
            == 0
        ):

            priorities.append(
                {
                    "severity": "warning",
                    "title": "No commercial pipeline",
                    "description": (
                        "No active quotations."
                    ),
                }
            )

        #
        # Future rules...
        #

        return priorities