import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from app.workspace.repositories.agreement_analytics_repository import (
    AgreementAnalyticsRepository,
)
from app.workspace.agreement_reference import normalize_product_reference


class AgreementAnalyticsService:
    """Owns agreement matching, comparisons and the analytics presentation model."""

    PAGE_SIZE = 50

    @classmethod
    def get_analytics(
        cls,
        customer_id: int,
        agreement: dict[str, Any] | None,
        *,
        search: str = "",
        status: str = "",
        page: int = 1,
    ) -> dict[str, Any] | None:
        if not agreement:
            return None
        customer = AgreementAnalyticsRepository.get_customer(customer_id)
        erp_id = (customer or {}).get("erp_customer_id") or ""
        items = AgreementAnalyticsRepository.list_items(agreement["id"])
        period = cls._period(agreement)
        if not erp_id or not period:
            return cls._empty(items, "Sin referencia histórica disponible")

        current_sales = AgreementAnalyticsRepository.list_sales(
            erp_id, period[0].isoformat(), period[1].isoformat()
        )
        previous = AgreementAnalyticsRepository.get_previous_agreement(
            customer_id, agreement["id"], agreement["start_date"]
        )
        comparison = cls._comparison_period(period, previous)
        previous_items = (
            AgreementAnalyticsRepository.list_items(previous["id"])
            if previous else items
        )
        previous_sales = AgreementAnalyticsRepository.list_sales(
            erp_id, comparison[0].isoformat(), comparison[1].isoformat()
        )
        known_keys = AgreementAnalyticsRepository.list_known_product_keys(erp_id)

        current_result = cls._allocate(items, current_sales, agreement.get("supplier"))
        previous_result = cls._allocate(
            previous_items, previous_sales,
            (previous or agreement).get("supplier"),
        )
        rows = cls._product_rows(
            items, current_result, previous_result, known_keys,
            agreement.get("supplier"), previous is not None,
        )
        account_revenue = sum(float(row["revenue"] or 0) for row in current_sales)
        agreement_revenue = current_result["revenue"]
        previous_revenue = previous_result["revenue"]
        negotiated = len(items)
        purchased = sum(1 for row in rows if row["current_purchased"])
        matched = sum(1 for row in rows if row["matched"])

        filtered = cls._filter_rows(rows, search, status)
        page = max(page, 1)
        start = (page - 1) * cls.PAGE_SIZE
        total_pages = max(1, (len(filtered) + cls.PAGE_SIZE - 1) // cls.PAGE_SIZE)
        return {
            "reference_label": (
                "Acuerdo anterior" if previous
                else "Referencia histórica estimada"
            ),
            "reference_detail": (
                previous.get("name") if previous
                else "Mismo universo de productos y periodo equivalente del año anterior"
            ),
            "period": cls._display_period(period),
            "comparison_period": cls._display_period(comparison),
            "negotiated_products": negotiated,
            "purchased_products": purchased,
            "coverage": purchased / negotiated * 100 if negotiated else 0,
            "never_purchased": sum(1 for row in rows if row["status"] == "never"),
            "never_sold": sum(1 for row in rows if not row["matched"]),
            "new_products": sum(1 for row in rows if row["status"] == "new"),
            "inactive_products": sum(1 for row in rows if row["status"] == "inactive"),
            "lost_products": cls._lost_count(items, previous_items) if previous else None,
            "lost_products_label": (
                str(cls._lost_count(items, previous_items))
                if previous else "Sin comparación histórica"
            ),
            "agreement_revenue": agreement_revenue,
            "display_agreement_revenue": cls._format_cop(agreement_revenue),
            "previous_revenue": previous_revenue,
            "display_previous_revenue": cls._format_cop(previous_revenue),
            "growth": cls._growth(agreement_revenue, previous_revenue),
            "account_revenue": account_revenue,
            "share_of_account": agreement_revenue / account_revenue * 100 if account_revenue else 0,
            "matching_success": matched / negotiated * 100 if negotiated else 0,
            "unmatched_products": negotiated - matched,
            "monthly": cls._monthly(current_sales, previous_sales, current_result, previous_result),
            "families": cls._families(current_result),
            "priorities": cls._priorities(rows),
            "products": filtered[start:start + cls.PAGE_SIZE],
            "pagination": {
                "page": page, "pages": total_pages, "total": len(filtered),
                "has_previous": page > 1, "has_next": page < total_pages,
            },
            "filters": {"q": search, "status": status},
        }

    @staticmethod
    def _period(agreement: dict[str, Any]) -> tuple[date, date] | None:
        try:
            start = date.fromisoformat(agreement.get("start_date") or "")
            end = date.fromisoformat(agreement.get("end_date") or "")
        except ValueError:
            return None
        effective_end = min(end, date.today())
        return (start, effective_end) if effective_end >= start else None

    @classmethod
    def _comparison_period(cls, period, previous):
        elapsed = (period[1] - period[0]).days
        if previous and previous.get("start_date") and previous.get("end_date"):
            start = date.fromisoformat(previous["start_date"])
            end = min(date.fromisoformat(previous["end_date"]), start + timedelta(days=elapsed))
            return start, end
        return cls._shift_year(period[0], -1), cls._shift_year(period[1], -1)

    @staticmethod
    def _shift_year(value: date, years: int) -> date:
        year = value.year + years
        return value.replace(year=year, day=min(value.day, calendar.monthrange(year, value.month)[1]))

    @staticmethod
    def _normalize(value: Any) -> str:
        return normalize_product_reference(value)

    @classmethod
    def _candidates(cls, item: dict[str, Any]) -> set[str]:
        return {
            value for value in (
                cls._normalize(item.get("internal_sku")),
                cls._normalize(item.get("manufacturer_part_number")),
                cls._normalize(item.get("normalized_reference")),
                cls._normalize(item.get("part_number")),
            ) if value
        }

    @classmethod
    def _primary_reference(cls, item: dict[str, Any]) -> str:
        for key in ("manufacturer_part_number", "internal_sku", "normalized_reference", "part_number"):
            value = cls._normalize(item.get(key))
            if value:
                return value
        return ""

    @classmethod
    def _allocate(cls, items, sales, supplier):
        supplier_key = cls._normalize(supplier)
        lookup = defaultdict(list)
        references = {}
        for item in items:
            references[item["id"]] = cls._primary_reference(item)
            for candidate in cls._candidates(item):
                if item["id"] not in lookup[candidate]:
                    lookup[candidate].append(item["id"])
                if supplier_key:
                    if item["id"] not in lookup[candidate + supplier_key]:
                        lookup[candidate + supplier_key].append(item["id"])
        by_item = defaultdict(float)
        by_month = defaultdict(float)
        by_reference = defaultdict(float)
        families = defaultdict(float)
        matched_sales = []
        purchased_ids = set()
        for sale in sales:
            item_ids = lookup.get(cls._normalize(sale.get("product_key")), [])
            if not item_ids:
                continue
            purchased_ids.update(item_ids)
            item_id = item_ids[0]
            revenue = float(sale.get("revenue") or 0)
            by_item[item_id] += revenue
            by_reference[references[item_id]] += revenue
            month = date.fromisoformat(sale["sale_date"]).month
            by_month[month] += revenue
            families[sale.get("family_name") or "Sin clasificar"] += revenue
            matched_sales.append(sale)
        return {
            "by_item": by_item, "by_reference": by_reference,
            "by_month": by_month, "families": families,
            "revenue": sum(by_item.values()), "sales": matched_sales,
            "purchased_ids": purchased_ids,
        }

    @classmethod
    def _product_rows(cls, items, current, previous, known_keys, supplier, has_previous):
        known = {cls._normalize(key) for key in known_keys}
        supplier_key = cls._normalize(supplier)
        rows = []
        for item in items:
            current_revenue = current["by_item"].get(item["id"], 0)
            current_purchased = item["id"] in current["purchased_ids"]
            candidates = cls._candidates(item)
            previous_revenue = (
                previous["by_reference"].get(cls._primary_reference(item), 0)
                if has_previous else previous["by_item"].get(item["id"], 0)
            )
            matched = bool(candidates & known or {
                candidate + supplier_key for candidate in candidates if supplier_key
            } & known)
            if current_purchased and previous_revenue <= 0:
                product_status = "new"
            elif not current_purchased and previous_revenue > 0:
                product_status = "inactive"
            elif not current_purchased:
                product_status = "never"
            else:
                product_status = "active"
            rows.append({
                **item, "current_revenue": current_revenue,
                "current_purchased": current_purchased,
                "display_revenue": cls._format_cop(current_revenue),
                "previous_revenue": previous_revenue, "status": product_status,
                "status_label": {"new": "Nuevo", "inactive": "Inactivo", "never": "Nunca comprado", "active": "Activo"}[product_status],
                "matched": matched,
            })
        return rows

    @classmethod
    def _lost_count(cls, current, previous):
        current_refs = set().union(*(cls._candidates(item) for item in current)) if current else set()
        return sum(1 for item in previous if not cls._candidates(item) & current_refs)

    @staticmethod
    def _filter_rows(rows, search, status):
        needle = search.strip().casefold()
        return [row for row in rows if (
            not status or row["status"] == status
        ) and (
            not needle or needle in " ".join(str(row.get(key) or "") for key in (
                "internal_sku", "manufacturer_part_number", "description", "product_line"
            )).casefold()
        )]

    @staticmethod
    def _monthly(current_sales, previous_sales, current, previous):
        labels = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        months = sorted(set(current["by_month"]) | set(previous["by_month"]))
        return [{"month": month, "label": labels[month - 1],
                 "current": current["by_month"].get(month, 0),
                 "previous": previous["by_month"].get(month, 0)} for month in months]

    @staticmethod
    def _families(result):
        total = result["revenue"]
        return [{"name": name, "revenue": revenue,
                 "display_revenue": AgreementAnalyticsService._format_cop(revenue),
                 "share": revenue / total * 100 if total else 0}
                for name, revenue in sorted(result["families"].items(), key=lambda row: row[1], reverse=True)]

    @classmethod
    def _priorities(cls, rows):
        priorities = []
        families = defaultdict(lambda: {"total": 0, "purchased": 0})
        for row in rows:
            family = row.get("product_line") or "Sin línea de producto"
            families[family]["total"] += 1
            families[family]["purchased"] += int(row["current_purchased"])
        if families:
            family, values = min(
                families.items(),
                key=lambda entry: (
                    entry[1]["purchased"] / entry[1]["total"],
                    -entry[1]["total"],
                ),
            )
            coverage = values["purchased"] / values["total"] * 100
            priorities.append({
                "type": "Cobertura de familia", "title": family,
                "value": f"{coverage:.1f}%",
                "detail": f"{values['total'] - values['purchased']} de {values['total']} productos sin compra en el periodo",
                "tone": "warning",
                "impact_group": 1,
                "impact": values["total"] - values["purchased"],
            })
        declines = sorted(
            (row for row in rows if row["previous_revenue"] > row["current_revenue"]),
            key=lambda row: row["previous_revenue"] - row["current_revenue"],
            reverse=True,
        )
        if declines:
            row = declines[0]
            priorities.append({
                "type": "Mayor caída interanual",
                "title": row.get("manufacturer_part_number") or row.get("internal_sku") or "Producto negociado",
                "value": cls._format_cop(row["previous_revenue"] - row["current_revenue"]),
                "detail": "Disminución frente a la referencia histórica",
                "tone": "critical",
                "impact_group": 2,
                "impact": row["previous_revenue"] - row["current_revenue"],
            })
        never_sold = [row for row in rows if not row["matched"]]
        if never_sold:
            priorities.append({
                "type": "Desarrollo de demanda", "title": "Productos nunca vendidos",
                "value": str(len(never_sold)),
                "detail": "Negociados sin ventas en todo el historial disponible",
                "tone": "warning",
                "impact_group": 1,
                "impact": len(never_sold),
            })
        inactive = [row for row in rows if row["status"] == "inactive"]
        if inactive:
            priorities.append({
                "type": "Recuperación", "title": "Productos inactivos",
                "value": str(len(inactive)),
                "detail": "Tuvieron ventas en la referencia y ninguna en el periodo actual",
                "tone": "critical",
                "impact_group": 2,
                "impact": sum(row["previous_revenue"] for row in inactive),
            })
        priorities.sort(
            key=lambda priority: (priority["impact_group"], priority["impact"]),
            reverse=True,
        )
        for priority in priorities:
            priority.pop("impact", None)
            priority.pop("impact_group", None)
        return priorities

    @staticmethod
    def _growth(current, previous):
        if not previous:
            return {"value": None, "label": "Sin base comparable", "tone": "neutral"}
        value = (current - previous) / previous * 100
        return {"value": value, "label": f"{value:+.1f}%", "tone": "positive" if value >= 0 else "critical"}

    @staticmethod
    def _display_period(period):
        return f"{period[0].strftime('%d/%m/%Y')} – {period[1].strftime('%d/%m/%Y')}"

    @classmethod
    def _empty(cls, items, label):
        product_rows = [{
            **item, "current_revenue": 0, "previous_revenue": 0,
            "current_purchased": False,
            "display_revenue": cls._format_cop(0), "status": "never",
            "status_label": "Nunca comprado", "matched": False,
        } for item in items]
        return {
            "reference_label": label, "reference_detail": "",
            "negotiated_products": len(items), "purchased_products": 0,
            "coverage": 0, "never_purchased": len(items), "never_sold": len(items),
            "new_products": 0, "inactive_products": 0, "lost_products": None,
            "lost_products_label": "Sin comparación histórica", "agreement_revenue": 0,
            "display_agreement_revenue": cls._format_cop(0),
            "previous_revenue": 0, "display_previous_revenue": cls._format_cop(0),
            "growth": cls._growth(0, 0), "account_revenue": 0,
            "share_of_account": 0, "matching_success": 0,
            "unmatched_products": len(items), "monthly": [], "families": [],
            "priorities": cls._priorities(product_rows),
            "products": product_rows[:cls.PAGE_SIZE],
            "pagination": {"page": 1, "pages": 1, "total": len(items), "has_previous": False, "has_next": len(items) > cls.PAGE_SIZE},
            "filters": {"q": "", "status": ""},
        }

    @staticmethod
    def _format_cop(amount: float | int | None) -> str:
        return f"COP {float(amount or 0):,.0f}"
