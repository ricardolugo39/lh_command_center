from typing import Any

from app.workspace.repositories.linear_motion_repository import (
    LinearMotionRepository,
)


class LinearMotionService:
    BRAND_OPTIONS = {"": "Ambas", "THK": "THK", "Thomson": "Thomson"}

    @staticmethod
    def _cop(value: Any) -> str:
        return f"COP {float(value or 0):,.0f}".replace(",", ".")

    @classmethod
    def get_page(cls, requested_brand: str = "") -> dict[str, Any]:
        brand = requested_brand if requested_brand in cls.BRAND_OPTIONS else ""
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
        return {
            "brand": brand,
            "brand_label": cls.BRAND_OPTIONS[brand],
            "brand_options": cls.BRAND_OPTIONS,
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
            "commercial": LinearMotionRepository.commercial_coverage(brand),
        }
