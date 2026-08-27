from datetime import date, datetime
from typing import Any

from app.database.transaction import transactional
from app.workspace.repositories.customer_portfolio_repository import (
    CustomerPortfolioRepository,
)
from app.workspace.repositories.customer_repository import CustomerRepository
from app.workspace.policies.customer_portfolio_status_policy import (
    CustomerPortfolioStatusPolicy,
)
from app.workspace.constants.commercial_office import OFFICES


class CustomerPortfolioService:
    """Commercial portfolio rules and presentation orchestration."""

    PAGE_SIZE = 25
    FILTER_LABELS = {
        "": "Todos", "strategic": "Estratégicos", "agreement": "Con acuerdo",
        "no_agreement": "Sin acuerdo", "risk": "En riesgo",
        "inactive": "Sin actividad", "opportunities": "Con oportunidades",
        "no_sales": "Sin ventas",
    }
    SORTS = {"state", "name", "sales", "growth", "activity", "purchase", "opportunities"}

    @classmethod
    def get_dashboard(cls, *, search: str = "", quick_filter: str = "",
                      office: str = "", advisor: str = "",
                      current_advisor: str | None = None,
                      sort: str = "sales", direction: str = "desc", page: int = 1):
        quick_filter = quick_filter if quick_filter in cls.FILTER_LABELS else ""
        office = office if office in OFFICES else ""
        sort = sort if sort in cls.SORTS else "sales"
        direction = "asc" if direction == "asc" else "desc"
        page = max(page, 1)
        effective_advisor = current_advisor if advisor == "mine" else advisor
        if advisor == "mine" and not effective_advisor:
            advisor = ""
            effective_advisor = ""
        rows = CustomerPortfolioRepository.list_portfolio(
            search=search, quick_filter=quick_filter, office=office,
            advisor=effective_advisor, sort=sort,
            direction=direction, limit=cls.PAGE_SIZE,
            offset=(page - 1) * cls.PAGE_SIZE,
        )
        customers = [cls._present(row) for row in rows]
        stats = CustomerPortfolioRepository.get_statistics(office=office, advisor=effective_advisor)
        filter_stats = (
            CustomerPortfolioRepository.get_statistics(
                search=search, office=office, advisor=effective_advisor
            )
            if search else stats
        )
        dimensions = CustomerPortfolioRepository.get_dimensions()
        total = int(rows[0]["filtered_total"] if rows else 0)
        pages = max(1, (total + cls.PAGE_SIZE - 1) // cls.PAGE_SIZE)
        return {
            "customers": customers,
            "kpis": cls._kpis(stats),
            "filters": cls._filter_chips(filter_stats, quick_filter),
            "dimensions": dimensions,
            "current_advisor": current_advisor,
            "query": {"q": search, "filter": quick_filter,
                      "office": office, "advisor": advisor,
                      "sort": sort, "direction": direction},
            "pagination": {"page": page, "pages": pages, "total": total,
                           "has_previous": page > 1, "has_next": page < pages},
        }

    @classmethod
    def _present(cls, row):
        current = float(row.get("revenue_ytd") or 0)
        previous = float(row.get("revenue_ly") or 0)
        growth = (current - previous) / previous * 100 if previous else None
        activity_days = cls._days_since(row.get("last_activity"))
        purchase_days = cls._days_since(row.get("last_purchase_date"))
        status = cls._status(
            current, previous, purchase_days, activity_days,
            int(row.get("open_opportunities") or 0),
            bool(row.get("active_agreements")), bool(row.get("next_followup")),
        )
        return {
            **row,
            "display_revenue": cls._format_compact_cop(current),
            "exact_revenue": cls._format_cop(current),
            "growth": growth,
            "growth_label": f"{growth:+.1f}%" if growth is not None else "Sin base LY",
            "growth_tone": "positive" if growth is not None and growth >= 0 else "critical" if growth is not None else "neutral",
            "status": status,
            "last_activity_label": cls._format_date(row.get("last_activity")),
            "last_activity_age": f"Hace {activity_days} días" if activity_days is not None else "Sin actividad registrada",
            "purchase_days": purchase_days,
            "purchase_days_label": f"{purchase_days} días" if purchase_days is not None else "Nunca",
            "purchase_tone": (
                "positive" if purchase_days is not None and purchase_days <= 30
                else "warning" if purchase_days is not None and purchase_days <= 60
                else "critical"
            ),
            "agreement_label": row.get("agreement_name") or "Sin acuerdo",
            "additional_agreements": max(int(row.get("active_agreements") or 0) - 1, 0),
            "next_action": cls._next_action(row, activity_days, purchase_days),
        }

    @staticmethod
    def _status(current, previous, purchase_days, activity_days,
                open_opportunities=0, active_agreement=False,
                has_pending_action=False):
        return CustomerPortfolioStatusPolicy.classify(
            current=current, previous=previous, purchase_days=purchase_days,
            activity_days=activity_days, open_opportunities=open_opportunities,
            active_agreement=active_agreement,
            has_pending_action=has_pending_action,
        )

    @staticmethod
    def _next_action(row, activity_days, purchase_days):
        if row.get("next_followup"):
            return {"label": row["next_followup"], "detail": f"Vence {row['next_followup_date']}", "tone": "warning"}
        if int(row.get("open_quotes") or 0) > 0:
            return {"label": "Enviar propuesta", "detail": "Cotización pendiente", "tone": "warning"}
        if int(row.get("active_agreements") or 0) and (purchase_days is None or purchase_days > 60):
            return {"label": "Revisar acuerdo", "detail": "Compra bajo acuerdo inactiva", "tone": "warning"}
        if activity_days is None or activity_days > 60:
            return {"label": "Programar visita", "detail": "Actividad comercial vencida", "tone": "critical"}
        if int(row.get("open_opportunities") or 0) > 0:
            return {"label": "Seguimiento", "detail": "Oportunidad activa", "tone": "neutral"}
        return {"label": "Planificar contacto", "detail": "Mantener relación", "tone": "neutral"}

    @classmethod
    def _kpis(cls, stats):
        return [
            ("Clientes totales", int(stats.get("total") or 0)),
            ("Cuentas estratégicas", int(stats.get("strategic") or 0)),
            ("Con acuerdo activo", int(stats.get("agreement") or 0)),
            ("Sin compra > 60 días", int(stats.get("inactive_purchase") or 0)),
            ("Oportunidades abiertas", int(stats.get("open_opportunities") or 0)),
            ("Ventas YTD", cls._format_cop(stats.get("revenue_ytd"))),
        ]

    @classmethod
    def _filter_chips(cls, stats, active):
        keys = ["", "strategic", "agreement", "no_agreement", "risk", "inactive", "opportunities", "no_sales"]
        count_keys = {"": "total", "strategic": "strategic", "agreement": "agreement",
                      "no_agreement": "no_agreement", "risk": "risk", "inactive": "inactive",
                      "opportunities": "opportunities", "no_sales": "no_sales"}
        return [{"value": key, "label": cls.FILTER_LABELS[key],
                 "count": int(stats.get(count_keys[key]) or 0), "active": key == active}
                for key in keys]

    @staticmethod
    def _days_since(value):
        if not value:
            return None
        try:
            return max((date.today() - datetime.fromisoformat(str(value)[:19]).date()).days, 0)
        except ValueError:
            return None

    @staticmethod
    def _format_date(value):
        if not value:
            return "Sin actividad"
        try:
            return datetime.fromisoformat(str(value)[:19]).strftime("%d/%m/%Y")
        except ValueError:
            return str(value)

    @staticmethod
    def _format_cop(value):
        return f"COP {float(value or 0):,.0f}"

    @staticmethod
    def _format_compact_cop(value):
        amount = float(value or 0)
        absolute = abs(amount)
        if absolute >= 1_000_000_000:
            return f"COP {amount / 1_000_000_000:.2f} B"
        if absolute >= 1_000_000:
            return f"COP {amount / 1_000_000:.1f} M"
        if absolute >= 1_000:
            return f"COP {amount / 1_000:.1f} K"
        return f"COP {amount:,.0f}"

    @staticmethod
    @transactional
    def resolve_workspace(erp_customer_id: str) -> int:
        existing = CustomerRepository.find_by_erp_customer_id(erp_customer_id)
        if existing:
            return existing["id"]
        customer = CustomerPortfolioRepository.get_master_customer(erp_customer_id)
        if not customer:
            raise ValueError("El cliente ERP no existe.")
        return CustomerRepository.create_customer(customer["customer_name"], erp_customer_id)
