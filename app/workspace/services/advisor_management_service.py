from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.workspace.repositories.advisor_review_repository import AdvisorReviewRepository
from app.workspace.repositories.commercial_visit_repository import CommercialVisitRepository
from app.workspace.repositories.company_sales_repository import CompanySalesRepository
from app.workspace.constants.commercial_office import canonical_sales_rep
from app.workspace.services.company_sales_dashboard_service import CompanySalesDashboardService
from app.workspace.services.customer_detail_service import CustomerDetailService
from app.workspace.services.opportunity_list_service import OpportunityListService
from app.workspace.services.workspace_dashboard_service import WorkspaceDashboardService


class AdvisorManagementService:
    @classmethod
    def get_page(cls, advisor_name: str, office: str, period: str = "week") -> dict[str, Any]:
        period = period if period in {"week", "month"} else "week"
        start = date.today() - timedelta(days=7 if period == "week" else 30)
        opportunity_page = OpportunityListService.get_page(
            {"office": office, "sales_rep": advisor_name}
        )
        visits = CommercialVisitRepository.list_advisor(advisor_name)
        recent_visits = [
            visit for visit in visits
            if start.isoformat() <= str(visit.get("visit_date") or "")
            <= date.today().isoformat()
        ]
        sales_page = CompanySalesDashboardService.get_page(office)
        seller = next(
            (item for item in sales_page["seller_impacts"]
             if item["name"].strip().casefold() == advisor_name.strip().casefold()),
            None,
        )
        customers = cls._customer_summary(
            CompanySalesRepository.list_history(office), visits, advisor_name
        )
        return {
            "advisor": advisor_name, "office": office, "period": period,
            "period_start": start.isoformat(), "sales": seller,
            "opportunities": opportunity_page, "visits": recent_visits,
            "visit_total": len(recent_visits),
            "activities": WorkspaceDashboardService.get_dashboard(office, advisor_name),
            "reviews": AdvisorReviewRepository.list_advisor(advisor_name),
            "customers": customers,
        }

    @staticmethod
    def _customer_summary(sales_rows: list[dict[str, Any]], visits: list[dict[str, Any]],
                          advisor_name: str) -> list[dict[str, Any]]:
        today = date.today()
        customers: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"current": 0.0, "previous": 0.0,
                     "visits_current": 0, "visits_previous": 0,
                     "name": "Sin cliente", "erp_customer_id": ""}
        )
        canonical = canonical_sales_rep(advisor_name)
        for row in sales_rows:
            if canonical_sales_rep(row.get("sales_rep")) != canonical:
                continue
            try:
                sold_on = date.fromisoformat(str(row.get("sale_date") or "")[:10])
            except ValueError:
                continue
            if (sold_on.month, sold_on.day) > (today.month, today.day):
                continue
            if sold_on.year not in {today.year, today.year - 1}:
                continue
            key = str(row.get("customer_id") or row.get("customer_name") or "").strip()
            item = customers[key]
            item["name"] = str(row.get("customer_name") or "Sin cliente")
            item["erp_customer_id"] = str(row.get("customer_id") or "").strip()
            item["current" if sold_on.year == today.year else "previous"] += float(
                row.get("neto") or 0
            )
        for visit in visits:
            try:
                visited_on = date.fromisoformat(str(visit.get("visit_date") or "")[:10])
            except ValueError:
                continue
            if (visited_on.month, visited_on.day) > (today.month, today.day):
                continue
            if visited_on.year not in {today.year, today.year - 1}:
                continue
            key = str(visit.get("customer_erp_id") or visit.get("customer_id") or "").strip()
            item = customers[key]
            item["name"] = str(visit.get("customer_name") or visit.get("source_customer_name") or item["name"])
            if visit.get("customer_erp_id"):
                item["erp_customer_id"] = str(visit["customer_erp_id"]).strip()
            item[
                "visits_current" if visited_on.year == today.year
                else "visits_previous"
            ] += 1
        result = []
        for item in customers.values():
            delta = item["current"] - item["previous"]
            result.append({
                **item, "delta": delta,
                "display_current": CustomerDetailService.format_cop(item["current"]),
                "display_previous": CustomerDetailService.format_cop(item["previous"]),
                "display_delta": (("+" if delta > 0 else "-" if delta < 0 else "")
                                  + CustomerDetailService.format_cop(abs(delta))),
                "change": delta / item["previous"] * 100 if item["previous"] else None,
                "visit_change": (
                    (item["visits_current"] - item["visits_previous"])
                    / item["visits_previous"] * 100
                    if item["visits_previous"] else None
                ),
            })
        return sorted(
            result,
            key=lambda item: (item["current"], item["visits_current"]),
            reverse=True,
        )[:12]
