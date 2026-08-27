from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from datetime import date, datetime
from typing import Any

from app.workspace.constants.project_status import (
    ALL_STATUSES,
    PIPELINE_STATUS_ORDER,
    ProjectStatus,
)
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.services.project_health_service import ProjectHealthService
from app.workspace.services.quote_service import QuoteService
from app.workspace.constants.opportunity_origin import OpportunityOrigin
from app.workspace.constants.commercial_office import OFFICES, office_for_sales_rep


@dataclass(frozen=True)
class OpportunityFilters:
    status: str = ""
    sales_rep: str = ""
    health: str = ""
    customer_name: str = ""
    origin: str = ""

    @classmethod
    def from_query(cls, query: Mapping[str, Any]) -> "OpportunityFilters":
        values = {
            field: str(query.get(field, "")).strip()
            for field in cls.__dataclass_fields__
        }

        if values["status"] not in ALL_STATUSES:
            values["status"] = ""
        if values["origin"] not in OpportunityOrigin.ALL:
            values["origin"] = ""

        health_keys = {
            option["value"]
            for option in ProjectHealthService.filter_options()
        }
        if values["health"] not in health_keys:
            values["health"] = ""

        return cls(**values)

    def persistence_criteria(self) -> dict[str, str]:
        return {
            "status": self.status,
            "sales_rep": self.sales_rep,
            "customer_name": self.customer_name,
            "origin": self.origin,
        }

    def as_dict(self) -> dict[str, str]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }

    @property
    def is_active(self) -> bool:
        return any(self.as_dict().values())


class OpportunityListService:

    @staticmethod
    def get_page(query: Mapping[str, Any]) -> dict[str, Any]:
        filters = OpportunityFilters.from_query(query)
        include_closed = str(query.get("include_closed", "")).strip().lower() in {
            "1", "true", "yes"
        }
        office = str(query.get("office", "")).strip()
        if office not in OFFICES:
            office = ""
        criteria = filters.persistence_criteria()
        if include_closed:
            criteria["include_closed"] = "1"
        if office:
            criteria["office"] = office
        records = ProjectRepository.list_project_overviews(
            criteria
        )

        opportunities = [
            OpportunityListService._present(record)
            for record in records
        ]

        if filters.health:
            opportunities = [
                opportunity
                for opportunity in opportunities
                if opportunity["health"]["key"] == filters.health
            ]

        attention = str(query.get("attention", "")).strip()
        if attention == "without_next_action":
            opportunities = [
                item for item in opportunities if not item.get("next_action_date")
            ]
        elif attention == "overdue":
            today = date.today().isoformat()
            opportunities = [
                item for item in opportunities
                if item.get("next_action_date")
                and str(item["next_action_date"]) < today
            ]
        elif attention == "at_risk":
            opportunities = [
                item for item in opportunities
                if item.get("health", {}).get("key") == "at_risk"
            ]
        else:
            attention = ""

        status_order = (*PIPELINE_STATUS_ORDER, ProjectStatus.CANCELLED)

        presented = {
            "opportunities": opportunities,
            "filters": {**filters.as_dict(), "include_closed": "1" if include_closed else "", "office": office, "attention": attention},
            "has_active_filters": filters.is_active or include_closed or bool(office) or bool(attention),
            "filter_options": {
                "statuses": [
                    {
                        "value": status,
                        "label": ProjectStatus.label(status),
                    }
                    for status in status_order
                ],
                "sales_representatives": (
                    ProjectRepository.list_sales_representatives()
                ),
                "health": ProjectHealthService.filter_options(),
                "origins": [
                    {"value": value, "label": OpportunityOrigin.label(value)}
                    for value in (
                        OpportunityOrigin.MANUAL,
                        OpportunityOrigin.CRM,
                        OpportunityOrigin.QUOTE,
                        OpportunityOrigin.VISIT,
                        OpportunityOrigin.RFQ,
                    )
                ],
                "offices": OFFICES,
            },
        }
        presented["pipeline"] = OpportunityListService._pipeline_summary(
            opportunities
        )
        presented["attention"] = OpportunityListService._attention_summary(
            opportunities
        )
        return presented

    @staticmethod
    def _present(record: dict[str, Any]) -> dict[str, Any]:
        last_activity_at = None
        if record.get("last_activity_at"):
            last_activity_at = (
                ProjectHealthService.parse_activity_timestamp(
                    record["last_activity_at"]
                )
            )

        health = ProjectHealthService.calculate_summary(
            project_status=record["status"],
            has_overdue_followup=bool(
                record.get("has_overdue_followup")
            ),
            last_activity_at=last_activity_at,
        )

        quote = None
        if record.get("quote_id") is not None:
            quote = QuoteService.enrich_quote(
                {
                    "id": record["quote_id"],
                    "project_id": record["id"],
                    "prefix": record.get("quote_prefix") or "CTC",
                    "quote_number": record.get("quote_number"),
                    "quote_date": record.get("quote_date"),
                    "amount": record.get("quote_amount"),
                    "currency_code": (
                        record.get("quote_currency_code") or "COP"
                    ),
                    "exchange_rate": record.get("quote_exchange_rate"),
                    "exchange_rate_type": record.get(
                        "quote_exchange_rate_type"
                    ),
                    "normalized_amount": record.get(
                        "quote_normalized_amount"
                    ),
                    "quote_status": record.get("quote_status"),
                    "revision": record.get("quote_revision") or 0,
                }
            )

        commercial_value = OpportunityListService.present_commercial_value(
            record,
            quote,
            record.get("crm_potential_value"),
        )

        return {
            **record,
            "office": office_for_sales_rep(record.get("sales_rep")),
            "commercial_amount_display": commercial_value["approved_display"],
            "commercial_value": commercial_value,
            "status_label": ProjectStatus.label(record.get("status")),
            "origin": record.get("origin") or OpportunityOrigin.MANUAL,
            "origin_label": OpportunityOrigin.label(record.get("origin")),
            "quote": quote,
            "health": health,
            "source_date_label": OpportunityListService._source_date_label(
                record.get("crm_source_date") or record.get("created_at")
            ),
        }

    @staticmethod
    def _source_date_label(value: Any) -> str:
        if not value:
            return "Fecha desconocida"
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            return str(value)
        age = (date.today() - parsed).days
        if age == 0:
            age_label = "hoy"
        elif age > 0:
            age_label = f"hace {age} días"
        else:
            age_label = f"en {abs(age)} días"
        return f"{parsed.isoformat()} · {age_label}"

    @staticmethod
    def _pipeline_summary(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for status in PIPELINE_STATUS_ORDER[:4]:
            items = [item for item in opportunities if item.get("status") == status]
            total = Decimal("0")
            for item in items:
                value = item.get("commercial_amount")
                if value in (None, "") and item.get("quote"):
                    value = item["quote"].get("normalized_amount")
                if value in (None, ""):
                    value = item.get("crm_potential_value")
                if value not in (None, ""):
                    total += Decimal(str(value))
            result.append({
                "status": status,
                "label": ProjectStatus.label(status),
                "count": len(items),
                "value": total,
                "value_display": OpportunityListService._compact_cop(total),
            })
        return result

    @staticmethod
    def _attention_summary(opportunities: list[dict[str, Any]]) -> dict[str, int]:
        today = date.today().isoformat()
        return {
            "without_next_action": sum(
                not item.get("next_action_date") for item in opportunities
            ),
            "overdue": sum(
                bool(item.get("next_action_date"))
                and str(item["next_action_date"]) < today
                for item in opportunities
            ),
            "at_risk": sum(
                item.get("health", {}).get("key") == "at_risk"
                for item in opportunities
            ),
        }

    @staticmethod
    def _compact_cop(value: Decimal) -> str:
        absolute = abs(value)
        if absolute >= Decimal("1000000000"):
            return f"COP {value / Decimal('1000000000'):.1f} B"
        if absolute >= Decimal("1000000"):
            return f"COP {value / Decimal('1000000'):.1f} M"
        return f"COP {value:,.0f}"

    @staticmethod
    def present_commercial_value(
        opportunity: Mapping[str, Any],
        quote: Mapping[str, Any] | None,
        crm_potential_value: Any = None,
    ) -> dict[str, str | None]:
        """Present the canonical list/detail commercial value consistently."""
        amount = opportunity.get("commercial_amount")
        if amount not in (None, ""):
            display = (
                f"{opportunity.get('commercial_currency') or 'COP'} "
                f"{Decimal(str(amount)):,.2f}"
            )
            return {
                "display": display,
                "detail": "Monto comercial aprobado",
                "approved_display": display,
            }

        if quote:
            return {
                "display": quote.get("display_amount") or "Sin cotización",
                "detail": quote.get("display_quote_number") or "Cotización",
                "approved_display": None,
            }

        if crm_potential_value not in (None, ""):
            return {
                "display": f"COP {Decimal(str(crm_potential_value)):,.2f}",
                "detail": "Potencial CRM · informativo",
                "approved_display": None,
            }

        return {
            "display": "Sin cotización",
            "detail": "Sin valor comercial registrado",
            "approved_display": None,
        }
