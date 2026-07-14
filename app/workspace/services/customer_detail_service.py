from typing import Any

from app.workspace.repositories.customer_detail_repository import (
    CustomerDetailRepository,
)
from app.workspace.repositories.customer_repository import (
    CustomerRepository,
)
from app.workspace.services.quote_service import (
    QuoteService,
)


class CustomerDetailService:

    @staticmethod
    def get_customer_page(
        customer_id: int,
    ) -> dict[str, Any]:
        customer = CustomerRepository.get_customer(
            customer_id
        )

        if customer is None:
            raise ValueError(
                f"Customer does not exist: {customer_id}"
            )

        erp_customer_id = (
            customer.get("erp_customer_id")
            or ""
        ).strip()

        erp_summary = None
        sites = []
        sales_summary = {
            "lifetime_sales": 0,
            "sales_last_12_months": 0,
            "sales_current_year": 0,
            "last_purchase_date": None,
            "document_count": 0,
        }
        recent_sales = []

        if erp_customer_id:
            erp_summary = (
                CustomerDetailRepository
                .get_erp_customer_summary(
                    erp_customer_id
                )
            )

            sites = (
                CustomerDetailRepository
                .list_customer_sites(
                    erp_customer_id
                )
            )

            sales_summary = (
                CustomerDetailRepository
                .get_sales_summary(
                    erp_customer_id
                )
            )

            recent_sales = (
                CustomerDetailRepository
                .list_recent_sales_documents(
                    erp_customer_id,
                    limit=10,
                )
            )

        projects = (
            CustomerDetailRepository
            .list_customer_projects(
                customer_id
            )
        )

        enriched_projects = []

        for project in projects:
            quote = None

            if project.get("quote_number"):
                quote = QuoteService.enrich_quote(
                    {
                        "id": None,
                        "project_id": project["id"],
                        "prefix": (
                            project.get("prefix")
                            or "CTC"
                        ),
                        "quote_number": project[
                            "quote_number"
                        ],
                        "amount": project.get(
                            "amount"
                        ),
                        "currency_code": (
                            project.get(
                                "currency_code"
                            )
                            or "COP"
                        ),
                        "exchange_rate": project.get(
                            "exchange_rate"
                        ),
                        "exchange_rate_type": None,
                        "normalized_amount": (
                            project.get(
                                "normalized_amount"
                            )
                        ),
                        "quote_date": None,
                        "quote_status": None,
                        "revision": 0,
                    }
                )

            enriched_projects.append(
                {
                    **project,
                    "quote": quote,
                }
            )

        pipeline_summary = (
            CustomerDetailRepository
            .get_pipeline_summary(
                customer_id
            )
        )

        return {
            "customer": customer,
            "erp_summary": erp_summary,
            "sites": sites,
            "projects": enriched_projects,
            "pipeline": pipeline_summary,
            "sales": {
                **sales_summary,
                "display_lifetime_sales": (
                    CustomerDetailService
                    .format_cop(
                        sales_summary.get(
                            "lifetime_sales"
                        )
                    )
                ),
                "display_last_12_months": (
                    CustomerDetailService
                    .format_cop(
                        sales_summary.get(
                            "sales_last_12_months"
                        )
                    )
                ),
                "display_current_year": (
                    CustomerDetailService
                    .format_cop(
                        sales_summary.get(
                            "sales_current_year"
                        )
                    )
                ),
            },
            "recent_sales": [
                {
                    **sale,
                    "display_net_amount": (
                        CustomerDetailService
                        .format_cop(
                            sale.get("net_amount")
                        )
                    ),
                    "display_discount_amount": (
                        CustomerDetailService
                        .format_cop(
                            sale.get(
                                "discount_amount"
                            )
                        )
                    ),
                }
                for sale in recent_sales
            ],
            "display_pipeline": (
                CustomerDetailService.format_cop(
                    pipeline_summary.get(
                        "open_pipeline_cop"
                    )
                )
            ),
        }

    @staticmethod
    def format_cop(
        amount: float | int | None,
    ) -> str:
        value = float(amount or 0)

        return f"COP {value:,.0f}"