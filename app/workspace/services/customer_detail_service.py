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

from app.workspace.builders.customer_priority_builder import (
    CustomerPriorityBuilder,
)

from app.workspace.builders.customer_insight_builder import (
    CustomerInsightBuilder,
)

from app.workspace.builders.customer_project_builder import (
    CustomerProjectBuilder,
)

from app.workspace.builders.customer_kpi_builder import (
    CustomerKPIBuilder,
)

from app.workspace.services.agreement_service import (
    AgreementService,
)

from app.workspace.builders.commercial_priority_builder import(
    CommercialPriorityBuilder
)

from app.workspace.builders.customer_tag_builder import (
    CustomerTagBuilder,
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

        projects = CustomerProjectBuilder.build(
            customer_id=customer_id
        )

        pipeline_summary = (
            CustomerDetailRepository
            .get_pipeline_summary(
                customer_id
            )
        )

        priorities = (
            CustomerPriorityBuilder.build(
                customer=customer,
                projects=projects,
                pipeline=pipeline_summary,
                sales=sales_summary,
            )
        )

        insights = CustomerInsightBuilder.build(
            sales={
                **sales_summary,
                "display_current_year": (
                    CustomerDetailService.format_cop(
                        sales_summary.get(
                            "sales_current_year"
                        )
                    )
                ),
                "display_last_12_months": (
                    CustomerDetailService.format_cop(
                        sales_summary.get(
                            "sales_last_12_months"
                        )
                    )
                ),
            },
            pipeline=pipeline_summary,
        )

        formatted_sales = {
            **sales_summary,
            "display_lifetime_sales": (
                CustomerDetailService.format_cop(
                    sales_summary.get(
                        "lifetime_sales"
                    )
                )
            ),
            "display_last_12_months": (
                CustomerDetailService.format_cop(
                    sales_summary.get(
                        "sales_last_12_months"
                    )
                )
            ),
            "display_current_year": (
                CustomerDetailService.format_cop(
                    sales_summary.get(
                        "sales_current_year"
                    )
                )
            ),
        }

        display_pipeline = (
            CustomerDetailService.format_cop(
                pipeline_summary.get(
                    "open_pipeline_cop"
                )
            )
        )

        agreements = AgreementService.list_customer(
            customer_id
        )

        active_agreement = (
            agreements[0]
            if agreements
            else None
        )
        
        kpis = CustomerKPIBuilder.build(
            sales=formatted_sales,
            pipeline=pipeline_summary,
            display_pipeline=display_pipeline,
            agreement=active_agreement,
        )

        tags = CustomerTagBuilder.build(
            customer=customer,
            agreement=active_agreement,
            pipeline=pipeline_summary,
        )

        

        priorities = CommercialPriorityBuilder.build(
            projects=projects,
            pipeline=pipeline_summary,
            agreement=active_agreement,
        )

        return {
            "customer": customer,
            "erp_summary": erp_summary,
            "sites": sites,
            "projects": projects,
            "pipeline": pipeline_summary,
            "priorities": priorities,
            "insights": insights,
            "sales": formatted_sales,
            "display_pipeline": display_pipeline,
            "kpis": kpis,
            "agreement": active_agreement,
            "priorities": priorities,
            "tags": tags,
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