from collections import defaultdict
from datetime import date
from typing import Any

from app.workspace.constants.commercial_office import OFFICES
from app.workspace.repositories.company_sales_repository import CompanySalesRepository
from app.workspace.services.customer_detail_service import CustomerDetailService
from app.workspace.services.strategic_account_service import StrategicAccountService


class CompanySalesDashboardService:
    @classmethod
    def get_page(cls, office: str = "") -> dict[str, Any]:
        office = office if office in OFFICES else ""
        history = CompanySalesRepository.list_history(office)
        all_history = history if not office else CompanySalesRepository.list_history()
        diagnosis = StrategicAccountService._sales_diagnosis(history)
        aligned = cls._aligned(history)
        customer_impacts = cls._impacts(aligned, "customer_name")
        seller_impacts = cls._impacts(aligned, "sales_rep")
        family_impacts = diagnosis["family_impacts"]
        decline = abs(float(diagnosis.get("delta") or 0)) or 1
        for item in customer_impacts:
            item["contribution"] = abs(item["delta"]) / decline * 100 if item["delta"] < 0 else 0
        return {
            "office": office,
            "scope_label": office or "Consolidado",
            "offices": OFFICES,
            "diagnosis": diagnosis,
            "monthly": cls._monthly(aligned),
            "office_summary": cls._office_summary(cls._aligned(all_history)),
            "customer_impacts": customer_impacts[:5],
            "seller_impacts": seller_impacts[:5],
            "family_impacts": family_impacts,
            "brand_impacts": diagnosis["brand_impacts"],
            "portfolio_shift": cls._portfolio_shift(aligned),
            "insights": cls._insights(diagnosis, family_impacts, seller_impacts, customer_impacts),
            "business_plan": cls._business_plan(diagnosis, family_impacts, seller_impacts, customer_impacts),
            "active_customers": {
                "current": len({r["customer_id"] for r in aligned["current"]}),
                "previous": len({r["customer_id"] for r in aligned["previous"]}),
            },
        }

    @staticmethod
    def _aligned(rows: list[dict[str, Any]], as_of: date | None = None):
        as_of = as_of or date.today()
        periods = {"current": [], "previous": []}
        for row in rows:
            try:
                sold_on = date.fromisoformat(str(row.get("sale_date") or "")[:10])
            except ValueError:
                continue
            if (sold_on.month, sold_on.day) > (as_of.month, as_of.day):
                continue
            if sold_on.year == as_of.year:
                periods["current"].append(row)
            elif sold_on.year == as_of.year - 1:
                periods["previous"].append(row)
        return periods

    @staticmethod
    def _monthly(periods):
        totals = {"current": defaultdict(float), "previous": defaultdict(float)}
        for period, rows in periods.items():
            for row in rows:
                month = int(str(row["sale_date"])[5:7])
                totals[period][month] += float(row.get("neto") or 0)
        return [{"month": month, "current": totals["current"][month],
                 "previous": totals["previous"][month]} for month in range(1, 13)]

    @classmethod
    def _office_summary(cls, periods):
        result = []
        for office in OFFICES:
            current = sum(float(r.get("neto") or 0) for r in periods["current"] if r.get("office") == office)
            previous = sum(float(r.get("neto") or 0) for r in periods["previous"] if r.get("office") == office)
            delta = current - previous
            result.append({"office": office, "current": current, "previous": previous,
                           "display_current": CustomerDetailService.format_cop(current),
                           "display_previous": CustomerDetailService.format_cop(previous),
                           "display_delta": StrategicAccountService._signed_cop(delta),
                           "change": delta / previous * 100 if previous else None})
        return result

    @staticmethod
    def _impacts(periods, field):
        current, previous = defaultdict(float), defaultdict(float)
        latest: dict[str, str] = {}
        for row in periods["current"]:
            name = str(row.get(field) or "Sin asignar")
            current[name] += float(row.get("neto") or 0)
            latest[name] = max(latest.get(name, ""), str(row.get("sale_date") or "")[:10])
        for row in periods["previous"]:
            previous[str(row.get(field) or "Sin asignar")] += float(row.get("neto") or 0)
        result = []
        for name in set(current) | set(previous):
            delta = current[name] - previous[name]
            result.append({"name": name, "current": CustomerDetailService.format_cop(current[name]),
                           "previous": CustomerDetailService.format_cop(previous[name]),
                           "current_value": current[name], "previous_value": previous[name],
                           "delta": delta, "display_delta": StrategicAccountService._signed_cop(delta),
                           "change": delta / previous[name] * 100 if previous[name] else None,
                           "last_purchase": latest.get(name) or "Sin compra YTD"})
        result = sorted(result, key=lambda item: item["delta"])
        maximum = max((abs(item["delta"]) for item in result), default=1) or 1
        for item in result:
            item["bar_width"] = abs(item["delta"]) / maximum * 100
        return result

    @staticmethod
    def _portfolio_shift(periods):
        current, previous = defaultdict(float), defaultdict(float)
        for row in periods["current"]:
            current[str(row.get("family_name") or "Sin clasificar")] += float(row.get("neto") or 0)
        for row in periods["previous"]:
            previous[str(row.get("family_name") or "Sin clasificar")] += float(row.get("neto") or 0)
        current_total, previous_total = sum(current.values()) or 1, sum(previous.values()) or 1
        names = sorted(set(current) | set(previous), key=lambda name: current[name], reverse=True)[:6]
        return [{"name": name, "current_share": current[name]/current_total*100,
                 "previous_share": previous[name]/previous_total*100,
                 "change_pp": current[name]/current_total*100-previous[name]/previous_total*100,
                 "display_current": CustomerDetailService.format_cop(current[name]),
                 "display_delta": StrategicAccountService._signed_cop(current[name]-previous[name]),
                 "change": (current[name]-previous[name])/previous[name]*100 if previous[name] else None}
                for name in names]

    @staticmethod
    def _insights(diagnosis, families, sellers, customers):
        decline = abs(float(diagnosis.get("delta") or 0)) or 1
        negative_families = [item for item in families if item["delta"] < 0]
        top_family = negative_families[0] if negative_families else None
        seller_loss = abs(sum(item["delta"] for item in sellers[:4] if item["delta"] < 0))
        growing = [item["name"].title() for item in families if item["delta"] > 0]
        top_customer = customers[0] if customers else None
        insights = []
        if top_family:
            insights.append({"title": f"{top_family['name'].title()} concentra el deterioro",
                             "observation": f"Su impacto es {top_family['display_delta']}, equivalente al {abs(top_family['delta'])/decline*100:.0f}% de la caída neta.",
                             "implication": "La prioridad es recuperar consumo y referencias del negocio principal, no solo aumentar categorías pequeñas.",
                             "action": "Abrir los clientes y referencias que explican esa categoría."})
        if sellers:
            insights.append({"title": "La caída está concentrada en el equipo",
                             "observation": f"Los cuatro mayores impactos suman {CustomerDetailService.format_cop(seller_loss)} de pérdida bruta.",
                             "implication": "Un plan general para toda la fuerza comercial diluiría el esfuerzo donde realmente está la brecha.",
                             "action": "Revisar cartera, compras extraordinarias y referencias perdidas por vendedor."})
        if top_customer:
            insights.append({"title": f"{top_customer['name']} es la primera cuenta a investigar",
                             "observation": f"Aporta {top_customer['display_delta']} a la variación y su última compra YTD fue {top_customer['last_purchase']}.",
                             "implication": "Una sola cuenta puede alterar materialmente el resultado de la sede; primero debe separarse calendario de pérdida estructural.",
                             "action": "Abrir el diagnóstico del cliente antes de atribuir la caída a competencia."})
        if growing:
            insights.append({"title": "Hay categorías con crecimiento",
                             "observation": f"{', '.join(growing[:3])} compensan parcialmente la caída del core.",
                             "implication": "Existe demanda para una oferta técnica complementaria, aunque todavía no reemplaza el negocio perdido.",
                             "action": "Identificar clientes donde replicar esa venta cruzada."})
        return insights[:3]

    @staticmethod
    def _business_plan(diagnosis, families, sellers, customers):
        top_family = next((item for item in families if item["delta"] < 0), None)
        top_customer_names = ", ".join(item["name"] for item in customers[:3]) or "las cuentas con mayor caída"
        top_sellers = ", ".join(item["name"] for item in sellers[:3]) or "los vendedores con mayor brecha"
        return [
            {"period": "30 días", "title": "Explicar la brecha",
             "actions": [f"Auditar {top_customer_names}.",
                         f"Separar compras extraordinarias, referencias perdidas, precio y volumen en {top_family['name'].title() if top_family else 'la categoría principal'}.",
                         "Registrar una causa confirmada y una próxima acción por cuenta."],
             "measure": "Cobertura de diagnóstico sobre las 20 cuentas que más explican la caída."},
            {"period": "60 días", "title": "Recuperar el negocio recurrente",
             "actions": [f"Ejecutar planes de recuperación con {top_sellers}.",
                         "Priorizar referencias recurrentes perdidas y validar disponibilidad, precio y sustitución.",
                         "Relacionar visitas, RFQs y oportunidades con cada brecha de venta."],
             "measure": "Valor recuperado, referencias reactivadas y acciones vencidas."},
            {"period": "90 días", "title": "Construir crecimiento repetible",
             "actions": ["Replicar servicios y lubricación en clientes con base instalada compatible.",
                         "Medir cobertura de pipeline contra la brecha restante.",
                         "Revisar semanalmente sede, vendedor, cliente, familia y marca."],
             "measure": "Pipeline de recuperación, conversión y nueva venta recurrente."},
        ]
