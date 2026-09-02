from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import Any

from app.database.connection import get_connection
from app.workspace.constants.commercial_office import canonical_sales_rep
from app.workspace.repositories.commercial_visit_repository import (
    CommercialVisitRepository,
)
from app.workspace.repositories.company_sales_repository import CompanySalesRepository
from app.workspace.services.customer_detail_service import CustomerDetailService
from app.workspace.services.opportunity_list_service import OpportunityListService


class AdvisorMonthlyReportService:
    """Closed-month management view backed by sales, visits and opportunities."""

    @classmethod
    def get_page(
        cls, advisor_name: str, office: str, month: str
    ) -> dict[str, Any]:
        year, month_number = cls._parse_month(month)
        start = date(year, month_number, 1)
        end = date(
            year + (month_number == 12),
            1 if month_number == 12 else month_number + 1,
            1,
        )
        sales = cls._sales(advisor_name, office, start, end)
        visits = cls._visits(advisor_name, start, end)
        opportunities = cls._opportunities(advisor_name, start, end)
        pipeline = OpportunityListService.get_page(
            {"office": office, "sales_rep": advisor_name}
        )
        signals = cls._signals(sales, visits, opportunities, pipeline)
        return {
            "advisor": advisor_name,
            "office": office,
            "month": start.strftime("%Y-%m"),
            "month_label": cls._month_label(start),
            "period_start": start.isoformat(),
            "period_end": date.fromordinal(end.toordinal() - 1).isoformat(),
            "sales": sales,
            "visits": visits,
            "opportunities": opportunities,
            "pipeline": pipeline,
            "signals": signals,
            "generated_on": date.today().isoformat(),
            "transition_note": (
                "Agosto de 2026 es la línea base: las oportunidades fueron "
                "migradas desde el ERP y enriquecidas en la aplicación."
                if start == date(2026, 8, 1) else None
            ),
        }

    @staticmethod
    def _parse_month(value: str) -> tuple[int, int]:
        try:
            parsed = date.fromisoformat(f"{value}-01")
        except ValueError as exc:
            raise ValueError("El período debe tener formato AAAA-MM.") from exc
        if parsed > date.today().replace(day=1):
            raise ValueError("No se puede generar un reporte de un mes futuro.")
        return parsed.year, parsed.month

    @classmethod
    def _sales(
        cls, advisor_name: str, office: str, start: date, end: date
    ) -> dict[str, Any]:
        rows = CompanySalesRepository.list_history(office, months=36)
        canonical = canonical_sales_rep(advisor_name)
        previous_month_end = start
        previous_month_start = (
            date(start.year - 1, 12, 1)
            if start.month == 1 else date(start.year, start.month - 1, 1)
        )
        previous_start = start.replace(year=start.year - 1)
        previous_end = end.replace(year=end.year - 1)
        current = previous_month = previous = ytd = previous_ytd = 0.0
        customers: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "name": "Sin cliente", "current": 0.0,
                "previous_month": 0.0, "previous": 0.0,
                "last_purchase": None,
            }
        )
        brands: dict[str, dict[str, Any]] = defaultdict(cls._sales_bucket)
        products: dict[str, dict[str, Any]] = defaultdict(cls._sales_bucket)
        for row in rows:
            if canonical_sales_rep(row.get("sales_rep")) != canonical:
                continue
            try:
                sold_on = date.fromisoformat(str(row.get("sale_date") or "")[:10])
            except ValueError:
                continue
            amount = float(row.get("neto") or 0)
            key = str(row.get("customer_id") or row.get("customer_name") or "")
            item = customers[key]
            item["name"] = str(row.get("customer_name") or "Sin cliente")
            if sold_on < end and (
                item["last_purchase"] is None or sold_on > item["last_purchase"]
            ):
                item["last_purchase"] = sold_on
            brand = cls._brand(row.get("product_id"))
            product_key = str(row.get("product_id") or "Sin referencia").strip()
            brand_item = brands[brand]
            product_item = products[product_key]
            product_item["name"] = str(row.get("product_name") or product_key)
            product_item["brand"] = brand
            if start <= sold_on < end:
                current += amount
                item["current"] += amount
                brand_item["current"] += amount
                brand_item["customers"].add(key)
                product_item["current"] += amount
                product_item["customers"].add(item["name"])
            elif previous_month_start <= sold_on < previous_month_end:
                previous_month += amount
                item["previous_month"] += amount
                brand_item["previous_month"] += amount
                product_item["previous_month"] += amount
            elif previous_start <= sold_on < previous_end:
                previous += amount
                item["previous"] += amount
                brand_item["previous"] += amount
                product_item["previous"] += amount
            if sold_on.year == start.year and sold_on < end:
                ytd += amount
            elif sold_on.year == start.year - 1 and sold_on < previous_end:
                previous_ytd += amount
        visits = CommercialVisitRepository.list_advisor(advisor_name)
        visit_index: dict[str, list[date]] = defaultdict(list)
        for visit in visits:
            try:
                visited_on = date.fromisoformat(str(visit.get("visit_date") or "")[:10])
            except ValueError:
                continue
            if visited_on >= end:
                continue
            visit_key = str(
                visit.get("customer_erp_id") or visit.get("customer_id")
                or visit.get("source_customer_name") or ""
            ).strip()
            visit_index[visit_key].append(visited_on)
        presented_customers = []
        for key, item in customers.items():
            customer_visits = visit_index.get(key, [])
            last_visit = max(customer_visits) if customer_visits else None
            visits_90 = sum(
                (end.toordinal() - 90) <= value.toordinal() < end.toordinal()
                for value in customer_visits
            )
            delta = item["current"] - item["previous"]
            presented_customers.append({
                **item,
                "last_purchase": item["last_purchase"].isoformat()
                if item["last_purchase"] else None,
                "last_visit": last_visit.isoformat() if last_visit else None,
                "visits_90": visits_90,
                "delta": delta,
                "change": cls._change(item["current"], item["previous"]),
                "previous_month_change": cls._change(
                    item["current"], item["previous_month"]
                ),
                "display_current": cls._cop(item["current"]),
                "display_previous_month": cls._cop(item["previous_month"]),
                "display_previous": cls._cop(item["previous"]),
            })
        top_customers = sorted(
            presented_customers, key=lambda item: item["current"], reverse=True
        )[:10]
        customer_movements = {
            "lost_previous_month": sorted(
                [item for item in presented_customers if not item["current"] and item["previous_month"] > 0],
                key=lambda item: item["previous_month"], reverse=True,
            )[:12],
            "lost_previous_year": sorted(
                [item for item in presented_customers if not item["current"] and item["previous"] > 0],
                key=lambda item: item["previous"], reverse=True,
            )[:12],
            "declining": sorted(
                [item for item in presented_customers if item["current"] > 0 and item["previous"] > 0 and (item["change"] or 0) <= -20],
                key=lambda item: item["delta"],
            )[:12],
            "new_or_recovered": sorted(
                [item for item in presented_customers if item["current"] > 0 and not item["previous"]],
                key=lambda item: item["current"], reverse=True,
            )[:12],
        }
        return {
            "current": current,
            "previous_month": previous_month,
            "previous": previous,
            "delta": current - previous,
            "change": cls._change(current, previous),
            "ytd": ytd,
            "previous_ytd": previous_ytd,
            "ytd_change": cls._change(ytd, previous_ytd),
            "display_current": cls._cop(current),
            "display_previous_month": cls._cop(previous_month),
            "display_previous": cls._cop(previous),
            "display_ytd": cls._cop(ytd),
            "display_previous_ytd": cls._cop(previous_ytd),
            "customers": top_customers,
            "customer_movements": customer_movements,
            "brands": cls._present_mix(brands, current, limit=20),
            "products": cls._present_mix(products, current, limit=25),
        }

    @staticmethod
    def _sales_bucket() -> dict[str, Any]:
        return {
            "name": "", "brand": "", "current": 0.0,
            "previous_month": 0.0, "previous": 0.0, "customers": set(),
        }

    @classmethod
    def _present_mix(
        cls, values: dict[str, dict[str, Any]], total: float, *, limit: int
    ) -> list[dict[str, Any]]:
        result = []
        for key, item in values.items():
            if not any((item["current"], item["previous_month"], item["previous"])):
                continue
            result.append({
                **item,
                "key": key,
                "customers": sorted(item["customers"]),
                "customer_count": len(item["customers"]),
                "share": item["current"] / total * 100 if total else 0,
                "change": cls._change(item["current"], item["previous"]),
                "display_current": cls._cop(item["current"]),
                "display_previous_month": cls._cop(item["previous_month"]),
                "display_previous": cls._cop(item["previous"]),
            })
        return sorted(
            result,
            key=lambda item: max(
                item["current"], item["previous_month"], item["previous"]
            ),
            reverse=True,
        )[:limit]

    @staticmethod
    def _brand(product_id: Any) -> str:
        value = str(product_id or "").upper().replace(" ", "")
        aliases = (
            ("REXROTH", ("REXROTH", "RTH")), ("SCHAEFFLER", ("FAG", "INA")),
            ("THOMSON", ("THOMSON", "THO")), ("SKF", ("SKF",)),
            ("NTN", ("NTN",)), ("THK", ("THK",)), ("NQK", ("NQK",)),
            ("KMK", ("KMK",)), ("TIMKEN", ("TIMKEN",)),
            ("KOYO", ("KOYO",)), ("DODGE", ("DODGE",)),
            ("HIWIN", ("HIWIN",)), ("TREN", ("TREN",)),
        )
        for label, codes in aliases:
            if any(value.endswith(code) for code in codes):
                return label
        return "Otra / sin identificar"

    @staticmethod
    def _visits(advisor_name: str, start: date, end: date) -> dict[str, Any]:
        all_visits = CommercialVisitRepository.list_advisor(advisor_name)
        visits = [
            visit for visit in all_visits
            if start.isoformat() <= str(visit.get("visit_date") or "") < end.isoformat()
        ]
        customers = {
            str(visit.get("customer_erp_id") or visit.get("source_customer_name") or "")
            for visit in visits
        }
        actionable = sum(bool(visit.get("requires_action")) for visit in visits)
        return {
            "total": len(visits),
            "customers": len(customers - {""}),
            "with_action": actionable,
            "items": visits,
        }

    @staticmethod
    def _opportunities(advisor_name: str, start: date, end: date) -> dict[str, Any]:
        sql = """
        SELECT p.*, c.name customer_name,
               (SELECT COUNT(*) FROM ws_activities a WHERE a.project_id=p.id) activity_count,
               (SELECT COUNT(*) FROM ws_commercial_approvals ca WHERE ca.project_id=p.id) approval_count
        FROM ws_projects p
        JOIN ws_customers c ON c.id=p.customer_id
        WHERE LOWER(TRIM(COALESCE(p.sales_rep,'')))=LOWER(TRIM(?))
          AND p.closed_at IS NOT NULL
          AND date(p.closed_at)>=date(?) AND date(p.closed_at)<date(?)
        ORDER BY p.closed_at DESC, p.id DESC
        """
        with get_connection() as connection:
            cursor = connection.execute(sql, (advisor_name, start.isoformat(), end.isoformat()))
            columns = [column[0] for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        closed = []
        for row in rows:
            try:
                source = json.loads(row.get("import_metadata") or "{}").get(
                    "source_facts", {}
                )
            except (TypeError, json.JSONDecodeError):
                source = {}
            amount = float(
                row.get("won_amount")
                or row.get("commercial_amount")
                or source.get("potential_value")
                or 0
            )
            complete_loss = bool(
                row.get("close_reason") and row.get("close_comments")
                and (row.get("competitor_company") or row.get("competitor_type"))
            )
            closed.append({
                **row,
                "amount": amount,
                "display_amount": AdvisorMonthlyReportService._cop(amount),
                "complete_loss": complete_loss,
                "has_escalation": int(row.get("approval_count") or 0) > 0,
            })
        won = [item for item in closed if item["status"] == "won"]
        lost = [item for item in closed if item["status"] == "lost"]
        return {
            "closed": closed,
            "won": won,
            "lost": lost,
            "won_count": len(won),
            "lost_count": len(lost),
            "won_value": sum(item["amount"] for item in won),
            "lost_value": sum(item["amount"] for item in lost),
            "won_value_display": AdvisorMonthlyReportService._cop(
                sum(item["amount"] for item in won)
            ),
            "lost_value_display": AdvisorMonthlyReportService._cop(
                sum(item["amount"] for item in lost)
            ),
            "documented_losses": sum(item["complete_loss"] for item in lost),
            "escalated_losses": sum(item["has_escalation"] for item in lost),
        }

    @staticmethod
    def _signals(sales, visits, opportunities, pipeline) -> list[dict[str, str]]:
        result = []
        if sales["change"] is not None and sales["change"] <= -20:
            result.append({"level": "critical", "title": "Ventas en retroceso", "detail": f"El mes cae {abs(sales['change']):.1f}% frente al mismo mes del año anterior."})
        if visits["total"] == 0:
            result.append({"level": "critical", "title": "Sin actividad registrada", "detail": "No hay visitas de AppSheet registradas durante el período."})
        lost_year = sales["customer_movements"]["lost_previous_year"]
        if lost_year:
            unvisited = sum(not item["visits_90"] for item in lost_year)
            result.append({
                "level": "critical", "title": "Clientes que dejaron de comprar",
                "detail": f"{len(lost_year)} clientes del mismo mes anterior no compraron; {unvisited} no tuvieron visita en los 90 días previos al cierre.",
            })
        brands = sales.get("brands", [])
        if brands and brands[0]["share"] >= 60:
            result.append({
                "level": "warning", "title": "Alta dependencia de una marca",
                "detail": f"{brands[0]['key']} representa {brands[0]['share']:.1f}% de las ventas del mes.",
            })
        pipeline_count = sum(item.get("count", 0) for item in pipeline["pipeline"])
        pipeline_value = sum(
            (item.get("value", 0) for item in pipeline["pipeline"]), start=0
        )
        if pipeline_count < 5:
            result.append({"level": "warning", "title": "Embudo insuficiente", "detail": f"El pipeline actual tiene {pipeline_count} oportunidades por {AdvisorMonthlyReportService._cop(pipeline_value)}."})
        if not result:
            result.append({"level": "good", "title": "Sin alertas críticas", "detail": "Los indicadores revisados no activan alertas gerenciales."})
        return result

    @staticmethod
    def _change(current: float, previous: float) -> float | None:
        return (current - previous) / previous * 100 if previous else None

    @staticmethod
    def _cop(value: float) -> str:
        return CustomerDetailService.format_cop(value)

    @staticmethod
    def _month_label(value: date) -> str:
        months = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
        return f"{months[value.month - 1].capitalize()} {value.year}"
