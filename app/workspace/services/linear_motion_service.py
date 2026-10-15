import csv
from io import BytesIO, StringIO
from typing import Any

from app.workspace.repositories.linear_motion_repository import (
    LinearMotionRepository,
)


class LinearMotionService:
    BRAND_OPTIONS = {"": "Ambas", "THK": "THK", "Thomson": "Thomson"}
    FOCUS_OPTIONS = {"": "Vista general", "guides": "Guías y rieles", "screws": "Tornillos de bolas"}

    @staticmethod
    def _cop(value: Any) -> str:
        return f"COP {float(value or 0):,.0f}".replace(",", ".")

    @classmethod
    def get_page(cls, requested_brand: str = "", requested_focus: str = "",
                 requested_segment: str = "") -> dict[str, Any]:
        brand = requested_brand if requested_brand in cls.BRAND_OPTIONS else ""
        focus = requested_focus if requested_focus in cls.FOCUS_OPTIONS else ""
        segment_options = LinearMotionRepository.segment_options()
        segment_lookup = {option.casefold(): option for option in segment_options}
        segment = segment_lookup.get(requested_segment.casefold())
        if not segment:
            segment = segment_lookup.get("plasticos", segment_options[0] if segment_options else "")
        summary = LinearMotionRepository.sales_summary(brand)
        current = float(summary.get("sales_ytd") or 0)
        previous = float(summary.get("sales_previous_ytd") or 0)
        family_rows = LinearMotionRepository.family_sales(brand)
        for row in family_rows:
            row["display_sales"] = cls._cop(row["sales_ytd"])
            prior = float(row.get("sales_previous_ytd") or 0)
            row["change"] = ((float(row["sales_ytd"]) - prior) / prior * 100) if prior else None
        city_rows = LinearMotionRepository.city_sales(brand)
        maximum_city = max((float(row["sales"] or 0) for row in city_rows), default=1) or 1
        for row in city_rows:
            row["display_sales"] = cls._cop(row["sales"])
            row["bar_width"] = float(row["sales"] or 0) / maximum_city * 100
        inventory = LinearMotionRepository.inventory(brand)
        for row in inventory:
            row["display_value"] = cls._cop(row["inventory_value"])
        coverage = LinearMotionRepository.customer_coverage(brand)
        buyers = int(coverage.get("buyers") or 0)
        coverage["city_percent"] = (coverage.get("with_city") or 0) / buyers * 100 if buyers else 0
        coverage["industry_percent"] = (coverage.get("with_activity") or 0) / buyers * 100 if buyers else 0
        segments = LinearMotionRepository.customer_segments(brand)
        maximum_segment = max((float(row["sales"] or 0) for row in segments), default=1) or 1
        for row in segments:
            row["display_sales"] = cls._cop(row["sales"])
            row["bar_width"] = float(row["sales"] or 0) / maximum_segment * 100
        diagnosis = LinearMotionRepository.diagnostic_breakdown(brand, focus)
        for rows in diagnosis.values():
            for row in rows:
                current_row, previous_row = float(row.get("current") or 0), float(row.get("previous") or 0)
                change = ((current_row - previous_row) / previous_row * 100) if previous_row else None
                row.update(delta=current_row-previous_row, display_current=cls._cop(current_row),
                           display_previous=cls._cop(previous_row), change=change,
                           display_change=f"{change:+.1f}%" if change is not None else "Nueva")
        return {
            "brand": brand,
            "brand_label": cls.BRAND_OPTIONS[brand],
            "target_label": brand or "movimiento lineal",
            "brand_options": cls.BRAND_OPTIONS,
            "focus": focus, "focus_label": cls.FOCUS_OPTIONS[focus],
            "focus_options": cls.FOCUS_OPTIONS,
            "summary": {
                **summary,
                "display_sales": cls._cop(current),
                "display_previous": cls._cop(previous),
                "change": ((current - previous) / previous * 100) if previous else None,
            },
            "monthly": LinearMotionRepository.monthly_sales(brand),
            "families": family_rows,
            "cities": city_rows,
            "inventory": inventory,
            "coverage": coverage,
            "segments": segments,
            "diagnosis": diagnosis,
            "segment": segment,
            "segment_options": segment_options,
            "segment_opportunity": (
                cls._format_segment_opportunity(
                    LinearMotionRepository.segment_opportunity(segment, brand)
                ) if segment else {}
            ),
            "commercial": LinearMotionRepository.commercial_coverage(brand),
        }

    @classmethod
    def _format_segment_opportunity(cls, result: dict[str, Any]) -> dict[str, Any]:
        for row in result.get("customers", []):
            row["display_other_sales"] = cls._cop(row.get("other_sales"))
        return result

    @classmethod
    def export_segment_opportunities(cls, requested_brand: str,
                                     requested_segment: str) -> tuple[BytesIO, str]:
        page = cls.get_page(requested_brand, "", requested_segment)
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "NIT", "Cliente", "Asesor ERP", "Ciudad", "Última compra",
            "Marcas que compra", "Marcas lineales competidoras", "Compras otras marcas",
        ])
        for row in page.get("segment_opportunity", {}).get("customers", []):
            writer.writerow([
                row.get("customer_id", ""), row.get("name", ""), row.get("advisor", ""),
                row.get("city", ""), row.get("last_purchase", ""), row.get("brands", ""),
                row.get("competitor_linear_brands", ""),
                round(float(row.get("other_sales") or 0), 2),
            ])
        stream = BytesIO(output.getvalue().encode("utf-8-sig"))
        stream.seek(0)
        safe_segment = "".join(character if character.isalnum() else "-" for character in page["segment"])
        return stream, f"oportunidades-{safe_segment.lower()}.csv"
