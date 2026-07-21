from typing import Any

from app.workspace.repositories.customer_detail_repository import (
    CustomerDetailRepository,
)
from app.workspace.services.quote_service import (
    QuoteService,
)


class CustomerProjectBuilder:

    @staticmethod
    def build(
        *,
        customer_id: int,
    ) -> list[dict[str, Any]]:
        projects = (
            CustomerDetailRepository
            .list_customer_projects(
                customer_id
            )
        )

        result = []
        seen_project_ids = set()

        for project in projects:
            project_id = project["id"]

            if project_id in seen_project_ids:
                continue

            seen_project_ids.add(project_id)

            quote = None

            if project.get("quote_number"):
                quote = QuoteService.enrich_quote(
                    {
                        "id": None,
                        "project_id": project_id,
                        "prefix": (
                            project.get("prefix")
                            or "CTC"
                        ),
                        "quote_number": (
                            project["quote_number"]
                        ),
                        "amount": project.get("amount"),
                        "currency_code": (
                            project.get("currency_code")
                            or "COP"
                        ),
                        "exchange_rate": project.get(
                            "exchange_rate"
                        ),
                        "exchange_rate_type": None,
                        "normalized_amount": project.get(
                            "normalized_amount"
                        ),
                        "quote_date": None,
                        "quote_status": None,
                        "revision": 0,
                    }
                )

            result.append(
                {
                    **project,
                    "quote": quote,
                    "last_activity": "—",
                    "next_action": "—",
                }
            )

        return result