from collections import defaultdict
from decimal import Decimal
from typing import Any

from app.workspace.services.company_sales_dashboard_service import CompanySalesDashboardService
from app.workspace.services.opportunity_list_service import OpportunityListService
from app.workspace.services.workspace_dashboard_service import WorkspaceDashboardService


class ManagerHomeService:
    """Compose the manager's branch view from canonical dashboard metrics."""

    @classmethod
    def get_page(cls, office: str) -> dict[str, Any]:
        sales = CompanySalesDashboardService.get_page(office)
        opportunity_page = OpportunityListService.get_page({"office": office})
        activities = WorkspaceDashboardService.get_dashboard(office)
        opportunities = opportunity_page["opportunities"]
        team: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "value": Decimal("0"), "at_risk": 0,
                     "without_next_action": 0}
        )
        for item in opportunities:
            row = team[str(item.get("sales_rep") or "Sin asignar")]
            row["count"] += 1
            value = item.get("commercial_amount")
            if value in (None, "") and item.get("quote"):
                value = item["quote"].get("normalized_amount")
            if value in (None, ""):
                value = item.get("crm_potential_value")
            if value not in (None, ""):
                row["value"] += Decimal(str(value))
            row["at_risk"] += item.get("health", {}).get("key") == "at_risk"
            row["without_next_action"] += not item.get("next_action_date")

        team_rows = [
            {"name": name, **values,
             "value_display": OpportunityListService._compact_cop(values["value"])}
            for name, values in team.items()
        ]
        team_rows.sort(key=lambda row: (row["at_risk"], row["count"]), reverse=True)
        pipeline_value = sum(
            (stage["value"] for stage in opportunity_page["pipeline"]), Decimal("0")
        )
        return {
            "office": office,
            "sales": sales["diagnosis"],
            "pipeline": opportunity_page["pipeline"],
            "pipeline_count": len(opportunities),
            "pipeline_value": OpportunityListService._compact_cop(pipeline_value),
            "attention": opportunity_page["attention"],
            "activities": activities["summary"],
            "team": team_rows,
        }
