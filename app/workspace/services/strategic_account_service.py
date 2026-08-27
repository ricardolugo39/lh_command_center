from datetime import date, datetime
from collections import Counter, defaultdict
from statistics import median, pstdev
from typing import Any

from app.workspace.constants.activity_types import ActivityType
from app.workspace.constants.agreement_status import get_status_label as get_agreement_status_label
from app.workspace.constants.project_status import get_status_label
from app.workspace.repositories.strategic_account_repository import (
    StrategicAccountRepository,
)
from app.workspace.services.customer_detail_service import CustomerDetailService
from app.workspace.services.agreement_analytics_service import AgreementAnalyticsService
from app.workspace.repositories.commercial_visit_repository import CommercialVisitRepository
from app.workspace.services.account_visit_analysis_service import AccountVisitAnalysisService


class StrategicAccountService:
    """Builds the executive presentation model for an account overview."""

    MEANINGFUL_ACTIVITY_TYPES = ActivityType.MANUAL_TYPES
    STATUS_COLORS = {
        "prospect": "blue",
        "quoting": "azure",
        "waiting_customer": "yellow",
        "negotiation": "orange",
        "won": "green",
        "lost": "red",
        "cancelled": "secondary",
    }
    ACTIVITY_ICONS = {
        "visit": "visit",
        "meeting": "meeting",
        "call": "call",
        "email": "email",
        "note": "note",
        "status_changed": "status",
        "project_created": "opportunity",
        "project_updated": "opportunity",
        "opportunity_closed": "opportunity",
    }

    @classmethod
    def get_overview(cls, customer_id: int) -> dict[str, Any]:
        account = StrategicAccountRepository.get_account(customer_id)
        if account is None:
            raise ValueError(f"Customer does not exist: {customer_id}")

        erp_id = (account.get("erp_customer_id") or "").strip()
        sales = cls._sales(erp_id)
        monthly = (
            StrategicAccountRepository.list_monthly_sales(erp_id)
            if erp_id else []
        )
        families = (
            StrategicAccountRepository.list_top_product_families(erp_id)
            if erp_id else []
        )
        activity = StrategicAccountRepository.get_activity_summary(customer_id)
        opportunities = StrategicAccountRepository.list_opportunities(customer_id)

        revenue = float(sales.get("revenue_ytd") or 0)
        previous = float(sales.get("revenue_previous_ytd") or 0)
        trend = cls._trend(revenue, previous)
        engagement = cls._engagement(activity)
        pipeline_value = sum(float(item.get("amount") or 0) for item in opportunities)
        health = cls._provisional_health(
            has_sales=bool(revenue or previous),
            growth=trend.get("value"),
            pipeline_value=pipeline_value,
            engagement=engagement,
        )

        raw_agreement = StrategicAccountRepository.get_agreement(customer_id)
        agreement_analytics = AgreementAnalyticsService.get_analytics(
            customer_id, raw_agreement
        ) if raw_agreement else None
        return {
            "account": account,
            "agreement": cls._present_agreement(raw_agreement),
            "agreement_analytics": agreement_analytics,
            "executive_summary": cls._executive_summary(
                health, trend, pipeline_value, engagement
            ),
            "kpis": cls._kpis(revenue, trend, opportunities, activity, agreement_analytics),
            "revenue_comparison": cls._revenue_comparison(monthly),
            "engagement": engagement,
            "activity_metrics": cls._activity_metrics(activity),
            "product_families": cls._product_families(families),
            "recent_activities": cls._recent_visits(customer_id),
            "opportunities": [
                cls._present_opportunity(item) for item in opportunities
            ],
            "visit_data": CommercialVisitRepository.customer_quality(customer_id),
            "visit_analysis": AccountVisitAnalysisService.state(customer_id),
        }

    @classmethod
    def get_products(cls, customer_id: int) -> dict[str, Any]:
        account = StrategicAccountRepository.get_account(customer_id)
        if not account:
            raise ValueError("El cliente no existe.")
        erp_id = str(account.get("erp_customer_id") or "").strip()
        sales = cls._sales(erp_id)
        monthly = StrategicAccountRepository.list_monthly_sales(erp_id) if erp_id else []
        families = StrategicAccountRepository.list_top_product_families(erp_id) if erp_id else []
        products = StrategicAccountRepository.list_top_products(erp_id) if erp_id else []
        history = StrategicAccountRepository.list_sales_history(erp_id) if erp_id else []
        behavior = cls._purchase_behavior(history)
        visits = CommercialVisitRepository.list_customer(customer_id)
        opportunities = StrategicAccountRepository.list_opportunities(customer_id)
        diagnosis = cls._sales_diagnosis(history, visits, opportunities)
        return {
            "account": account,
            "sales": {
                **sales,
                "display_revenue": CustomerDetailService.format_cop(sales.get("revenue_ytd")),
                "display_previous": CustomerDetailService.format_cop(sales.get("revenue_previous_ytd")),
                "trend": cls._trend(float(sales.get("revenue_ytd") or 0), float(sales.get("revenue_previous_ytd") or 0)),
            },
            "revenue_comparison": cls._revenue_comparison(monthly),
            "families": cls._product_families(families),
            "products": [{
                **row,
                "display_revenue": CustomerDetailService.format_cop(row.get("revenue")),
                "trend": cls._trend(float(row.get("revenue") or 0), float(row.get("previous_revenue") or 0)),
            } for row in products],
            "behavior": behavior,
            "diagnosis": diagnosis,
        }

    @classmethod
    def _sales_diagnosis(
        cls,
        rows: list[dict[str, Any]],
        visits: list[dict[str, Any]] | None = None,
        opportunities: list[dict[str, Any]] | None = None,
        as_of: date | None = None,
    ) -> dict[str, Any]:
        """Explain an aligned YTD change using deterministic, traceable drivers."""
        as_of = as_of or date.today()
        visits = visits or []
        opportunities = opportunities or []
        current_year, previous_year = as_of.year, as_of.year - 1
        current: list[dict[str, Any]] = []
        previous: list[dict[str, Any]] = []
        for row in rows:
            raw_date = str(row.get("sale_date") or "")[:10]
            if not raw_date:
                continue
            try:
                sold_on = date.fromisoformat(raw_date)
            except ValueError:
                continue
            if (sold_on.month, sold_on.day) > (as_of.month, as_of.day):
                continue
            if sold_on.year == current_year:
                current.append(row)
            elif sold_on.year == previous_year:
                previous.append(row)

        def value(items):
            return sum(float(item.get("neto") or 0) for item in items)

        def documents(items):
            return {
                f"{item.get('prefijo')}-{item.get('numero')}" for item in items
            }

        def document_values(items):
            totals: dict[str, float] = defaultdict(float)
            for item in items:
                totals[f"{item.get('prefijo')}-{item.get('numero')}"] += float(item.get("neto") or 0)
            return list(totals.values())

        current_value, previous_value = value(current), value(previous)
        delta = current_value - previous_value
        change = (delta / previous_value * 100) if previous_value else None
        current_tickets, previous_tickets = document_values(current), document_values(previous)
        current_median = median(current_tickets) if current_tickets else 0
        previous_median = median(previous_tickets) if previous_tickets else 0
        median_change = ((current_median - previous_median) / previous_median * 100) if previous_median else None
        current_days = len({str(item.get("sale_date"))[:10] for item in current})
        previous_days = len({str(item.get("sale_date"))[:10] for item in previous})

        def product_totals(items):
            totals: dict[str, float] = defaultdict(float)
            names: dict[str, str] = {}
            for item in items:
                key = str(item.get("product_id") or "Sin referencia").strip()
                totals[key] += float(item.get("neto") or 0)
                names[key] = str(item.get("product_name") or "").strip()
            return totals, names

        current_products, current_names = product_totals(current)
        previous_products, previous_names = product_totals(previous)
        current_keys, previous_keys = set(current_products), set(previous_products)
        lost_keys, new_keys = previous_keys-current_keys, current_keys-previous_keys
        retained_keys = current_keys & previous_keys
        retained_changes = {key: current_products[key]-previous_products[key] for key in retained_keys}
        components = [
            ("Referencias que no se repitieron", -sum(previous_products[key] for key in lost_keys), len(lost_keys), "lost"),
            ("Referencias nuevas", sum(current_products[key] for key in new_keys), len(new_keys), "new"),
            ("Recurrentes en caída", sum(v for v in retained_changes.values() if v < 0), sum(v < 0 for v in retained_changes.values()), "down"),
            ("Recurrentes creciendo", sum(v for v in retained_changes.values() if v >= 0), sum(v >= 0 for v in retained_changes.values()), "up"),
        ]

        def impact_rows(group_getter):
            cur: dict[str, float] = defaultdict(float)
            prev: dict[str, float] = defaultdict(float)
            for item in current:
                cur[group_getter(item)] += float(item.get("neto") or 0)
            for item in previous:
                prev[group_getter(item)] += float(item.get("neto") or 0)
            result = []
            for name in set(cur) | set(prev):
                item_delta = cur[name] - prev[name]
                result.append({
                    "name": name, "current": cur[name], "previous": prev[name],
                    "delta": item_delta, "display_delta": cls._signed_cop(item_delta),
                    "change": ((item_delta / prev[name]) * 100) if prev[name] else None,
                })
            result = sorted(result, key=lambda item: item["delta"])
            maximum = max((abs(item["delta"]) for item in result), default=1) or 1
            for item in result:
                item["bar_width"] = round(abs(item["delta"]) / maximum * 100)
                item["display_current"] = CustomerDetailService.format_cop(item["current"])
                item["display_previous"] = CustomerDetailService.format_cop(item["previous"])
            return result

        family_impacts = impact_rows(lambda item: str(item.get("family_name") or "Sin clasificar"))
        brand_impacts = impact_rows(lambda item: cls._brand(str(item.get("product_id") or "")))
        top_driver = family_impacts[0] if family_impacts else None
        lost_products = sorted(({
            "id": key,
            "name": previous_names.get(key) or current_names.get(key) or "",
            "previous": previous_products[key],
            "display_impact": cls._signed_cop(-previous_products[key]),
        } for key in lost_keys), key=lambda item: item["previous"], reverse=True)[:12]

        large_previous_docs = []
        if previous_tickets:
            ticket_threshold = max(median(previous_tickets) * 3, 1)
            by_doc: dict[str, dict[str, Any]] = {}
            for item in previous:
                key = f"{item.get('prefijo')}-{item.get('numero')}"
                entry = by_doc.setdefault(key, {"id": key, "date": str(item.get("sale_date"))[:10], "value": 0.0})
                entry["value"] += float(item.get("neto") or 0)
            large_previous_docs = sorted(
                ({**item, "display_value": CustomerDetailService.format_cop(item["value"])} for item in by_doc.values() if item["value"] >= ticket_threshold),
                key=lambda item: item["value"], reverse=True,
            )[:5]

        today = as_of
        pending = []
        for visit in visits:
            status = str(visit.get("visit_status") or "").lower()
            if not visit.get("requires_action") or status in {"cerrado", "closed", "completado"}:
                continue
            due = str(visit.get("commitment_date") or "")[:10]
            overdue = False
            try:
                overdue = bool(due and date.fromisoformat(due) < today)
            except ValueError:
                pass
            pending.append({
                "visit_id": visit.get("id"), "visit_date": str(visit.get("visit_date") or "")[:10],
                "action": visit.get("required_action") or "Acción pendiente",
                "due": due or "Sin fecha", "overdue": overdue,
            })
        pending.sort(key=lambda item: (not item["overdue"], item["due"]))

        visit_text = " ".join(str(v.get(field) or "") for v in visits[:8] for field in (
            "visit_reason", "executive_summary", "detected_need", "detected_risk", "competitor", "required_action"
        )).lower()
        sales_focus = any(term in visit_text for term in ("rodamiento", "ina", "fag", "skf", "referencia"))
        current_docs, previous_docs = len(documents(current)), len(documents(previous))
        if change is None:
            headline = "No existe una base comparable del año anterior."
        elif current_docs >= previous_docs * .9 and median_change is not None and median_change < -10:
            headline = f"La cuenta sigue comprando, pero con tickets más pequeños ({median_change:.0f}%)."
        elif current_docs < previous_docs:
            headline = f"La caída se explica principalmente por menos documentos ({current_docs} vs. {previous_docs})."
        else:
            headline = "El volumen de compra cambió, aunque la actividad documental se mantiene."
        if top_driver and top_driver["delta"] < 0:
            headline += f" {top_driver['name'].title()} concentra el mayor impacto ({top_driver['display_delta']})."

        unknowns = ["Confirmar si las referencias perdidas dejaron de consumirse, quedaron en inventario o pasaron a otro proveedor."]
        if large_previous_docs:
            unknowns.append("Validar si las compras grandes del año anterior correspondían a proyectos, paradas o reposición extraordinaria.")
        if any(item["name"] == "FAG" and item["current"] == 0 and item["previous"] > 0 for item in brand_impacts):
            unknowns.append("Investigar por qué FAG no registra compras en el periodo actual.")

        return {
            "headline": headline,
            "change": change,
            "delta": delta,
            "display_delta": cls._signed_cop(delta),
            "current": CustomerDetailService.format_cop(current_value),
            "previous": CustomerDetailService.format_cop(previous_value),
            "documents": {"current": current_docs, "previous": previous_docs},
            "purchase_days": {"current": current_days, "previous": previous_days},
            "ticket_median": {"current": CustomerDetailService.format_cop(current_median), "previous": CustomerDetailService.format_cop(previous_median), "change": median_change},
            "components": [{"label": label, "value": amount, "display_value": cls._signed_cop(amount), "count": count, "tone": tone} for label,amount,count,tone in components],
            "family_impacts": family_impacts,
            "brand_impacts": brand_impacts,
            "lost_products": lost_products,
            "large_previous_documents": large_previous_docs,
            "visit_reading": {
                "count": len(visits), "pending": pending[:6],
                "sales_focus": sales_focus,
                "message": ("Las visitas mencionan referencias o rodamientos, pero aún debe documentarse la causa de la variación." if sales_focus else "Las visitas recientes no documentan la causa de la pérdida del portafolio recurrente."),
            },
            "pipeline": {"count": len(opportunities), "value": CustomerDetailService.format_cop(sum(float(item.get("amount") or 0) for item in opportunities))},
            "unknowns": unknowns,
            "generated_for": as_of.isoformat(),
        }

    @staticmethod
    def _signed_cop(value: float) -> str:
        prefix = "+" if value > 0 else "-" if value < 0 else ""
        return f"{prefix}{CustomerDetailService.format_cop(abs(value))}"

    @classmethod
    def _purchase_behavior(cls, rows: list[dict[str, Any]]) -> dict[str, Any]:
        documents: dict[str, dict[str, Any]] = {}
        month_sales: dict[str, float] = defaultdict(float)
        month_documents: dict[str, set[str]] = defaultdict(set)
        month_types: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        month_brands: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        product_documents: Counter = Counter()
        brand_sales: Counter = Counter()
        type_sales: Counter = Counter()
        for row in rows:
            day = str(row.get("sale_date") or "")[:10]
            month = day[:7]
            document_id = f"{row.get('prefijo')}-{row.get('numero')}"
            value = float(row.get("neto") or 0)
            product = str(row.get("product_id") or "").strip()
            product_type = cls._product_type(row.get("family_name"))
            brand = cls._brand(product)
            document = documents.setdefault(document_id, {"id": document_id, "date": day, "value": 0.0, "products": set(), "types": Counter(), "brands": Counter()})
            document["value"] += value
            document["products"].add(product)
            document["types"][product_type] += value
            document["brands"][brand] += value
            month_sales[month] += value
            month_documents[month].add(document_id)
            month_types[month][product_type] += value
            month_brands[month][brand] += value
            product_documents[product] += 1
            brand_sales[brand] += value
            type_sales[product_type] += value
        ordered_documents = sorted(documents.values(), key=lambda item: item["date"])
        tickets = [item["value"] for item in ordered_documents]
        ticket_median = median(tickets) if tickets else 0
        ticket_average = sum(tickets) / len(tickets) if tickets else 0
        dates = sorted({datetime.fromisoformat(item["date"]).date() for item in ordered_documents if item["date"]})
        intervals = [(right-left).days for left,right in zip(dates,dates[1:])]
        interval_median = median(intervals) if intervals else None
        interval_cv = (pstdev(intervals)/(sum(intervals)/len(intervals))) if len(intervals)>1 and sum(intervals)>0 else None
        monthly_values = list(month_sales.values())
        monthly_median = median(monthly_values) if monthly_values else 0
        deviations = [abs(value-monthly_median) for value in monthly_values]
        mad = median(deviations) if deviations else 0
        threshold = max(monthly_median * 2, monthly_median + 3 * mad)
        anomalies = []
        for month,value in sorted(month_sales.items()):
            if value >= threshold and value > 0:
                docs = [documents[key] for key in month_documents[month]]
                prominent = max(month_types[month], key=month_types[month].get) if month_types[month] else "Sin clasificar"
                anomalies.append({"month": month, "value": value, "display_value": CustomerDetailService.format_cop(value), "median_ticket": median([item["value"] for item in docs]), "display_ticket": CustomerDetailService.format_cop(median([item["value"] for item in docs])), "mix": prominent, "confidence": "Alta" if value >= threshold*1.35 else "Media"})
        active_months = len(month_sales)
        recurrence = min(100, round((active_months/24*55) + ((1-min(interval_cv or 1,1))*25) + (sum(1 for count in product_documents.values() if count>1)/max(len(product_documents),1)*20)))
        anomaly_share = sum(item["value"] for item in anomalies)/max(sum(monthly_values),1)
        project_score = min(100, round(anomaly_share*100 + len(anomalies)/24*100))
        opportunity_score = max(0, min(100, 100-recurrence-project_score//2))
        label = "Recurrente"
        if recurrence >= 50 and project_score >= 15: label = "Recurrente con picos de proyecto"
        elif project_score >= 35: label = "Orientada a proyectos"
        elif recurrence < 35: label = "Compra de oportunidad"
        total = sum(monthly_values)
        top5 = sum(sorted(tickets, reverse=True)[:5])/max(sum(tickets),1)*100
        return {
            "label": label,
            "explanation": f"{active_months} meses activos de 24; mediana entre compras de {round(interval_median) if interval_median is not None else '—'} días; {len(anomalies)} meses atípicos.",
            "ticket_median": CustomerDetailService.format_cop(ticket_median),
            "ticket_average": CustomerDetailService.format_cop(ticket_average),
            "frequency": round(len(documents)/24,1),
            "top5_concentration": round(top5,1),
            "scores": {"recurring": recurrence, "project": project_score, "opportunity": opportunity_score},
            "monthly": [{"month": month, "sales": value, "documents": len(month_documents[month]), "anomaly": value>=threshold and value>0} for month,value in sorted(month_sales.items())],
            "type_mix": cls._mix(type_sales, total),
            "brand_mix": cls._mix(brand_sales, total),
            "type_series": [{"month": month, **values} for month,values in sorted(month_types.items())],
            "brand_series": [{"month": month, **values} for month,values in sorted(month_brands.items())],
            "anomalies": anomalies[-8:],
            "signals": cls._behavior_signals(recurrence, project_score, active_months, top5, anomalies, type_sales),
        }

    @staticmethod
    def _product_type(family: Any) -> str:
        value = str(family or "").upper()
        if "RODAM" in value or "CHUMAC" in value: return "Rodamientos"
        if any(term in value for term in ("TRANSM", "CADENA", "CORREA", "PIÑON")): return "Transmisión de potencia"
        return "Otros"

    @staticmethod
    def _brand(product: str) -> str:
        upper = product.upper().replace(" ", "")
        for brand in ("SKF", "NTN", "TREN", "HIWIN", "FAG", "INA", "TIMKEN", "KOYO", "DODGE"):
            if upper.endswith(brand) or brand in upper[-10:]: return brand
        return "Otros"

    @staticmethod
    def _mix(counter: Counter, total: float) -> list[dict[str, Any]]:
        return [{"name": key, "value": value, "share": value/max(total,1)*100, "display_value": CustomerDetailService.format_cop(value)} for key,value in counter.most_common()]

    @staticmethod
    def _behavior_signals(recurrence, project_score, active_months, top5, anomalies, type_sales):
        signals = [{"tone":"positive","title":"Cadencia de compra","detail":f"Actividad en {active_months} de los últimos 24 meses."}]
        risks = [{"tone":"warning","title":"Concentración de tickets","detail":f"Los 5 documentos principales representan {top5:.1f}% del valor."}]
        opportunities = []
        if anomalies: signals.append({"tone":"neutral","title":"Picos atípicos","detail":f"Se detectaron {len(anomalies)} meses compatibles con compras de proyecto."})
        if recurrence < 50: risks.append({"tone":"warning","title":"Baja recurrencia","detail":"La frecuencia sugiere compras puntuales o como proveedor alterno."})
        if type_sales:
            smallest = min(type_sales, key=type_sales.get)
            opportunities.append({"tone":"positive","title":f"Expandir {smallest.lower()}","detail":"Es la categoría con menor participación en el mix actual."})
        opportunities.append({"tone":"positive","title":"Anticipar picos","detail":"Usar los meses atípicos para preparar inventario y contacto comercial."})
        return {"signals":signals,"risks":risks,"opportunities":opportunities}

    @staticmethod
    def _sales(erp_id: str) -> dict[str, Any]:
        if not erp_id:
            return {"revenue_ytd": 0, "revenue_previous_ytd": 0}
        return StrategicAccountRepository.get_sales_summary(erp_id)

    @classmethod
    def _kpis(
        cls,
        revenue: float,
        trend: dict[str, Any],
        opportunities: list[dict[str, Any]],
        activity: dict[str, Any],
        agreement: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return [
            cls._kpi(
                "revenue", "Ingresos YTD",
                CustomerDetailService.format_cop(revenue),
                trend["label"],
                "Mismo periodo del año anterior",
                tone=trend["tone"], primary=True,
            ),
            cls._kpi(
                "pipeline", "Oportunidades abiertas", str(len(opportunities)),
                "Pipeline activo", "Oportunidades vigentes",
            ),
            cls._kpi(
                "visit", "Última visita",
                cls._format_date(activity.get("last_visit")),
                "Actividad registrada", "Visita comercial más reciente",
            ),
            cls._agreement_kpi(agreement, "agreement_revenue", "Ingresos del acuerdo", "display_agreement_revenue", "Productos negociados comprados"),
            cls._agreement_kpi(agreement, "coverage", "Cobertura", "coverage", "Productos negociados con compra", percentage=True),
            cls._agreement_kpi(agreement, "agreement", "Nunca comprados", "never_purchased", "Productos sin compras históricas"),
        ]

    @classmethod
    def _provisional_health(
        cls,
        *,
        has_sales: bool,
        growth: float | None,
        pipeline_value: float,
        engagement: dict[str, Any],
    ) -> dict[str, str]:
        """Presentation-only health; not a permanent account score."""
        if not has_sales and engagement["days_since"] is None:
            return {
                "label": "Sin información suficiente",
                "tone": "neutral",
                "description": "Estado provisional",
            }
        if (
            growth is not None and growth >= 0
            and (pipeline_value > 0 or engagement["status"] in {"Alta", "Media"})
        ):
            return {
                "label": "Saludable",
                "tone": "positive",
                "description": "Estado provisional",
            }
        return {
            "label": "Atención",
            "tone": "warning",
            "description": "Estado provisional",
        }

    @classmethod
    def _executive_summary(
        cls,
        health: dict[str, str],
        trend: dict[str, Any],
        pipeline_value: float,
        engagement: dict[str, Any],
    ) -> list[dict[str, str]]:
        return [
            {"label": "Estado de cuenta", "value": health["label"], "tone": health["tone"], "detail": health["description"]},
            {"label": "Ingresos", "value": trend["label"], "tone": trend["tone"], "detail": "frente al mismo periodo anterior"},
            {"label": "Pipeline", "value": CustomerDetailService.format_cop(pipeline_value), "tone": "neutral", "detail": "valor abierto"},
            {"label": "Última actividad", "value": engagement["last_activity"], "tone": engagement["tone"], "detail": engagement["activity_context"]},
            {"label": "Próxima acción", "value": engagement["follow_up"], "tone": engagement["tone"], "detail": "recomendación provisional"},
        ]

    @classmethod
    def _engagement(cls, activity: dict[str, Any]) -> dict[str, Any]:
        meaningful = activity.get("last_meaningful_activity")
        last_activity = meaningful or activity.get("last_activity")
        days = cls._days_since(meaningful)
        if days is None:
            status, tone, follow_up = "Sin registro", "neutral", "Programar contacto"
        elif days <= 14:
            status, tone, follow_up = "Alta", "positive", "Mantener seguimiento"
        elif days <= 45:
            status, tone, follow_up = "Media", "neutral", "Seguimiento este mes"
        else:
            status, tone, follow_up = "Baja", "warning", "Seguimiento esta semana"
        return {
            "status": status,
            "tone": tone,
            "last_visit": cls._format_date(activity.get("last_visit")),
            "last_activity": cls._format_date(last_activity),
            "days_since": days,
            "days_label": f"Hace {days} días" if days is not None else "Sin interacción comercial registrada",
            "follow_up": follow_up,
            "activity_context": (
                "Interacción comercial" if meaningful else "Actividad registrada"
            ),
        }

    @classmethod
    def _revenue_comparison(cls, rows: list[dict[str, Any]]) -> dict[str, Any]:
        by_month: dict[int, dict[str, float]] = {}
        for row in rows:
            month = int(row["month_number"])
            by_month.setdefault(month, {"current": 0, "previous": 0})[
                row["period"]
            ] = float(row.get("revenue") or 0)
        points = [
            {
                "month": month,
                "label": cls._month_label(month),
                "current": values["current"],
                "previous": values["previous"],
            }
            for month, values in sorted(by_month.items())
        ]
        return {
            "points": points,
            "has_current": any(point["current"] for point in points),
            "has_previous": any(point["previous"] for point in points),
            "current_total": sum(point["current"] for point in points),
            "previous_total": sum(point["previous"] for point in points),
            "display_current_total": CustomerDetailService.format_cop(sum(point["current"] for point in points)),
            "display_previous_total": CustomerDetailService.format_cop(sum(point["previous"] for point in points)),
        }

    @classmethod
    def _product_families(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(rows) > 5:
            rows = [*rows[:5], {
                "family_name": "Otras familias",
                "revenue": sum(float(row.get("revenue") or 0) for row in rows[5:]),
                "previous_revenue": sum(float(row.get("previous_revenue") or 0) for row in rows[5:]),
                "total_revenue": rows[0].get("total_revenue"),
            }]
        total = (
            float(rows[0].get("total_revenue") or 0)
            if rows and "total_revenue" in rows[0]
            else sum(float(row.get("revenue") or 0) for row in rows)
        )
        maximum = max((float(row.get("revenue") or 0) for row in rows), default=0)
        result = []
        for row in rows:
            revenue = float(row.get("revenue") or 0)
            previous = float(row.get("previous_revenue") or 0)
            growth = cls._trend(revenue, previous)
            result.append({
                **row,
                "display_revenue": CustomerDetailService.format_cop(revenue),
                "share": revenue / total * 100 if total else 0,
                "bar_width": revenue / maximum * 100 if maximum else 0,
                "growth_label": growth["label"] if previous > 0 else None,
                "growth_tone": growth["tone"],
            })
        return result

    @classmethod
    def _meaningful_recent_activity(
        cls, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        result = []
        audit_groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            activity_type = row.get("activity_type")
            if activity_type in cls.MEANINGFUL_ACTIVITY_TYPES:
                result.append(cls._present_activity(row, customer_facing=True))
                continue
            key = activity_type or "activity"
            group = audit_groups.setdefault(key, {**row, "count": 0})
            group["count"] += 1
        for group in audit_groups.values():
            presented = cls._present_activity(group, customer_facing=False)
            if group["count"] > 1:
                presented["title"] = (
                    f"{group['count']} eventos: {ActivityType.label(group.get('activity_type'))}"
                )
            result.append(presented)
        return result[:6]

    @classmethod
    def _present_activity(
        cls, row: dict[str, Any], *, customer_facing: bool
    ) -> dict[str, Any]:
        return {
            **row,
            "type_label": ActivityType.label(row.get("activity_type")),
            "icon": cls.ACTIVITY_ICONS.get(row.get("activity_type"), "system"),
            "display_date": cls._format_date(row.get("occurred_at")),
            "context_label": "Interacción comercial" if customer_facing else "Evento del sistema",
        }

    @classmethod
    def _recent_visits(cls, customer_id: int) -> list[dict[str, Any]]:
        return [{
            **visit,
            "title": f"Visita {str(visit.get('visit_type') or 'comercial').lower()}",
            "type_label": "AppSheet",
            "icon": "visit",
            "display_date": cls._format_date(visit.get("visit_date")),
            "context_label": visit.get("advisor_name") or "Visita comercial",
            "project_name": visit.get("detected_need") or visit.get("visit_reason") or "Sin detalle",
        } for visit in CommercialVisitRepository.list_customer(customer_id)[:6]]

    @classmethod
    def _present_agreement(cls, agreement: dict[str, Any] | None) -> dict[str, Any]:
        if agreement is None:
            return {"name": "Acuerdo estratégico", "status_label": "Sin información", "period": "Periodo por definir", "is_temporary": True}
        return {
            **agreement,
            "status_label": get_agreement_status_label(agreement.get("status")),
            "period": f"{cls._format_date(agreement.get('start_date'))} — {cls._format_date(agreement.get('end_date'))}",
            "is_temporary": False,
            "readiness_label": f"{agreement.get('item_count', 0)} productos negociados",
            "days_remaining": cls._days_until(agreement.get("end_date")),
        }

    @classmethod
    def _present_opportunity(cls, item: dict[str, Any]) -> dict[str, Any]:
        return {
            **item,
            "status_label": get_status_label(item.get("status")),
            "status_color": cls.STATUS_COLORS.get(item.get("status"), "secondary"),
            "display_amount": CustomerDetailService.format_cop(item.get("amount")),
            "has_value": float(item.get("amount") or 0) > 0,
        }

    @staticmethod
    def _activity_metrics(activity: dict[str, Any]) -> list[tuple[str, int]]:
        return [("Visitas", int(activity.get("visits") or 0)), ("Visitas técnicas", int(activity.get("technical_visits") or 0)), ("Acciones pendientes", int(activity.get("pending_actions") or 0)), ("Oportunidades", int(activity.get("opportunities") or 0)), ("Cotizaciones", int(activity.get("quotes") or 0))]

    @staticmethod
    def _kpi(icon: str, label: str, value: str, trend: str, subtitle: str, *, tone: str = "neutral", primary: bool = False) -> dict[str, Any]:
        return {"icon": icon, "label": label, "value": value, "trend": trend, "subtitle": subtitle, "tone": tone, "primary": primary, "temporary": False}

    @classmethod
    def _temporary_kpi(cls, label: str, value: str, subtitle: str) -> dict[str, Any]:
        return {**cls._kpi("", label, value, "", subtitle), "temporary": True}

    @classmethod
    def _agreement_kpi(cls, analytics, icon, label, key, subtitle, percentage=False):
        if not analytics:
            return cls._temporary_kpi(label, "Sin acuerdo", subtitle)
        value = analytics.get(key, 0)
        if percentage:
            value = f"{float(value):.1f}%"
        return cls._kpi(icon, label, str(value), analytics["reference_label"], subtitle)

    @staticmethod
    def _trend(current: float, previous: float) -> dict[str, Any]:
        if previous <= 0:
            return {"value": None, "label": "Sin comparativo", "tone": "neutral"}
        value = (current - previous) / previous * 100
        return {"value": value, "label": f"{value:+.1f}%", "tone": "positive" if value >= 0 else "critical"}

    @staticmethod
    def _days_since(value: str | None) -> int | None:
        if not value:
            return None

    @staticmethod
    def _days_until(value: str | None) -> int | None:
        if not value:
            return None
        try:
            return (datetime.fromisoformat(value[:10]).date() - date.today()).days
        except ValueError:
            return None
        try:
            return max((date.today() - datetime.fromisoformat(value[:19]).date()).days, 0)
        except ValueError:
            return None

    @staticmethod
    def _format_date(value: str | None) -> str:
        if not value:
            return "Sin registro"
        try:
            parsed = datetime.fromisoformat(value[:19])
            months = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
            return f"{parsed.day:02d} {months[parsed.month - 1]} {parsed.year}"
        except ValueError:
            return value

    @staticmethod
    def _month_label(month: int) -> str:
        return ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")[month - 1]
