from __future__ import annotations

import math
import re
from typing import Any

from app.database.transaction import transaction


DEFAULT_RULES = (
    ("BLOQUE", "HSR", 58.0),
    ("BLOQUE", "SHS", 58.0),
    ("BLOQUE", "SR", 58.0),
    ("BLOQUE", "SSR", 58.0),
    ("BLOQUE", "HRW", 46.0),
    ("RIEL", "HSR", 68.0),
    ("RIEL", "SHS", 58.0),
    ("RIEL", "SR", 57.0),
    ("RIEL", "GENERAL", 58.0),
    ("RODAMIENTO", "GENERAL", 58.0),
    ("CHUMACERA", "GENERAL", 44.0),
    ("GRASA", "GENERAL", 59.0),
    ("OTRO", "GENERAL", 58.0),
)


class BrandPricingService:
    """Versioned, explainable final-price simulations for managed brands."""

    @classmethod
    def overview(cls, profile_code: str = "THK") -> dict[str, Any]:
        with transaction(write=False) as connection:
            profile = connection.execute(
                """SELECT * FROM stock_planning_vendor_profiles
                WHERE UPPER(profile_code)=UPPER(?)""", (profile_code,),
            ).fetchone()
            if not profile:
                raise ValueError("La marca no está configurada.")
            snapshot = connection.execute(
                """SELECT id,snapshot_key,as_of_date FROM stock_planning_snapshots
                WHERE vendor_profile_id=? AND archived_at IS NULL
                ORDER BY id DESC LIMIT 1""", (profile["id"],),
            ).fetchone()
            scenarios = connection.execute(
                """SELECT s.*,
                    (SELECT COUNT(*) FROM brand_pricing_line_decisions d
                     WHERE d.scenario_id=s.id AND d.decision_status='approved')
                        approved_count
                FROM brand_pricing_scenarios s
                WHERE s.vendor_profile_id=? ORDER BY s.id DESC""",
                (profile["id"],),
            ).fetchall()
        return {
            "profile": dict(profile),
            "snapshot": dict(snapshot) if snapshot else None,
            "scenarios": [dict(row) for row in scenarios],
        }

    @classmethod
    def create(
        cls, profile_code: str, name: str, trm: float, created_by: str,
    ) -> int:
        if trm <= 0:
            raise ValueError("La TRM debe ser mayor que cero.")
        overview = cls.overview(profile_code)
        if not overview["snapshot"]:
            raise ValueError("La marca no tiene un análisis de inventario disponible.")
        with transaction(write=True) as connection:
            cursor = connection.execute(
                """INSERT INTO brand_pricing_scenarios (
                    vendor_profile_id,scenario_name,source_snapshot_id,trm,
                    import_factor,rail_increment_percent,rounding_increment,
                    created_by
                ) VALUES (?,?,?,?,1.2,17,100,?)""",
                (
                    overview["profile"]["id"], name.strip() or "Análisis THK",
                    overview["snapshot"]["id"], trm, created_by,
                ),
            )
            scenario_id = int(cursor.lastrowid)
            connection.executemany(
                """INSERT INTO brand_pricing_rules (
                    scenario_id,product_type,series,gross_margin_percent,
                    rule_source,updated_by
                ) VALUES (?,?,?,?,?,?)""",
                [
                    (scenario_id, product_type, series, margin, "inferred", created_by)
                    for product_type, series, margin in DEFAULT_RULES
                ],
            )
        return scenario_id

    @classmethod
    def detail(cls, scenario_id: int) -> dict[str, Any]:
        with transaction(write=False) as connection:
            scenario = connection.execute(
                """SELECT s.*,v.vendor_name,v.profile_code,ss.snapshot_key,
                    ss.as_of_date
                FROM brand_pricing_scenarios s
                JOIN stock_planning_vendor_profiles v
                    ON v.id=s.vendor_profile_id
                JOIN stock_planning_snapshots ss ON ss.id=s.source_snapshot_id
                WHERE s.id=?""", (scenario_id,),
            ).fetchone()
            if not scenario:
                raise ValueError("El análisis de precios no existe.")
            rules = [dict(row) for row in connection.execute(
                """SELECT * FROM brand_pricing_rules
                WHERE scenario_id=? ORDER BY product_type,series""",
                (scenario_id,),
            ).fetchall()]
            products = [dict(row) for row in connection.execute(
                """SELECT p.internal_sku,p.vendor_sku,p.product_name,
                    f.fob_usd,f.lista1_cop
                FROM stock_planning_snapshot_products p
                LEFT JOIN stock_planning_snapshot_fob_prices f
                    ON f.snapshot_id=p.snapshot_id
                   AND f.internal_sku=p.internal_sku
                WHERE p.snapshot_id=? ORDER BY p.internal_sku""",
                (scenario["source_snapshot_id"],),
            ).fetchall()]
            decisions = {
                row["internal_sku"]: dict(row)
                for row in connection.execute(
                    """SELECT * FROM brand_pricing_line_decisions
                    WHERE scenario_id=?""", (scenario_id,),
                ).fetchall()
            }
            accepted_quotes = [dict(row) for row in connection.execute(
                """SELECT h.internal_sku,h.branch_code,h.accepted_fob_usd,
                    h.accepted_at
                FROM stock_planning_quote_price_history h
                JOIN (
                    SELECT internal_sku,branch_code,MAX(id) latest_id
                    FROM stock_planning_quote_price_history
                    WHERE snapshot_id=? GROUP BY internal_sku,branch_code
                ) latest ON latest.latest_id=h.id""",
                (scenario["source_snapshot_id"],),
            ).fetchall()]
        quote_prices: dict[str, list[dict[str, Any]]] = {}
        for row in accepted_quotes:
            quote_prices.setdefault(row["internal_sku"], []).append(row)
        lines = cls._calculate(
            dict(scenario), rules, products, decisions, quote_prices
        )
        eligible = [line for line in lines if line["calculated_price_cop"] is not None]
        return {
            "scenario": dict(scenario), "rules": rules, "lines": lines,
            "summary": {
                "total": len(lines),
                "with_list_price": sum(line["list_price_cop"] is not None for line in lines),
                "missing_list_price": sum(line["list_price_cop"] is None for line in lines),
                "calculable": len(eligible),
                "approved": sum(bool(line["decision"]) for line in lines),
                "large_changes": sum(
                    line["variance_percent"] is not None
                    and abs(line["variance_percent"]) >= 20 for line in eligible
                ),
            },
        }

    @classmethod
    def update_settings(
        cls, scenario_id: int, trm: float, rail_increment: float,
        rounding_increment: int, updated_by: str,
    ) -> None:
        if trm <= 0:
            raise ValueError("La TRM debe ser mayor que cero.")
        if not 0 <= rail_increment <= 200:
            raise ValueError("El incremento de riel debe estar entre 0% y 200%.")
        if rounding_increment not in {1, 100, 1000, 5000}:
            raise ValueError("Seleccione una regla de redondeo válida.")
        with transaction(write=True) as connection:
            cls._require_draft(connection, scenario_id)
            connection.execute(
                """UPDATE brand_pricing_scenarios
                SET trm=?,rail_increment_percent=?,rounding_increment=?,
                    updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (trm, rail_increment, rounding_increment, scenario_id),
            )
            connection.execute(
                "DELETE FROM brand_pricing_line_decisions WHERE scenario_id=?",
                (scenario_id,),
            )

    @classmethod
    def update_rule(
        cls, scenario_id: int, rule_id: int, margin: float, updated_by: str,
    ) -> None:
        if not 0 <= margin < 100:
            raise ValueError("El margen bruto debe estar entre 0% y 100%.")
        with transaction(write=True) as connection:
            cls._require_draft(connection, scenario_id)
            cursor = connection.execute(
                """UPDATE brand_pricing_rules SET gross_margin_percent=?,
                    rule_source='manual',updated_by=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND scenario_id=?""",
                (margin, updated_by, rule_id, scenario_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("La regla de margen no existe.")
            connection.execute(
                "DELETE FROM brand_pricing_line_decisions WHERE scenario_id=?",
                (scenario_id,),
            )

    @classmethod
    def approve_many(
        cls, scenario_id: int, skus: list[str], decided_by: str,
        price_choice: str = "calculated",
    ) -> int:
        if price_choice not in {"calculated", "current"}:
            raise ValueError("Seleccione una decisión de precio válida.")
        selected = {sku.strip() for sku in skus if sku.strip()}
        if not selected:
            raise ValueError("Seleccione al menos una referencia.")
        detail = cls.detail(scenario_id)
        if detail["scenario"]["status"] != "draft":
            raise ValueError("El análisis está cerrado.")
        lines = [
            line for line in detail["lines"]
            if line["internal_sku"] in selected
            and (
                line["calculated_price_cop"] is not None
                if price_choice == "calculated"
                else line["list_price_cop"] is not None
            )
        ]
        if len(lines) != len(selected):
            raise ValueError("Alguna referencia seleccionada no puede calcularse.")
        with transaction(write=True) as connection:
            connection.executemany(
                """INSERT INTO brand_pricing_line_decisions (
                    scenario_id,internal_sku,approved_price_cop,
                    calculated_price_cop,decision_status,decided_by,price_choice
                ) VALUES (?,?,?,?, 'approved', ?,?)
                ON CONFLICT(scenario_id,internal_sku) DO UPDATE SET
                    approved_price_cop=excluded.approved_price_cop,
                    calculated_price_cop=excluded.calculated_price_cop,
                    decision_status='approved',decided_by=excluded.decided_by,
                    decided_at=CURRENT_TIMESTAMP,
                    price_choice=excluded.price_choice""",
                [
                    (
                        scenario_id, line["internal_sku"],
                        (
                            line["calculated_price_cop"]
                            if price_choice == "calculated"
                            else line["list_price_cop"]
                        ),
                        line["calculated_price_cop"] or 0,
                        decided_by, price_choice,
                    )
                    for line in lines
                ],
            )
        return len(lines)

    @classmethod
    def close(cls, scenario_id: int) -> int:
        detail = cls.detail(scenario_id)
        valid_skus = [
            line["internal_sku"] for line in detail["lines"] if line["decision"]
        ]
        if not valid_skus:
            raise ValueError("Apruebe al menos una referencia antes de cerrar.")
        with transaction(write=True) as connection:
            cls._require_draft(connection, scenario_id)
            placeholders = ",".join("?" for _ in valid_skus)
            connection.execute(
                f"""DELETE FROM brand_pricing_line_decisions
                WHERE scenario_id=? AND internal_sku NOT IN ({placeholders})""",
                (scenario_id, *valid_skus),
            )
            connection.execute(
                """UPDATE brand_pricing_scenarios
                SET status='approved',updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (scenario_id,),
            )
        return len(valid_skus)

    @staticmethod
    def _require_draft(connection, scenario_id: int) -> None:
        row = connection.execute(
            "SELECT status FROM brand_pricing_scenarios WHERE id=?",
            (scenario_id,),
        ).fetchone()
        if not row:
            raise ValueError("El análisis de precios no existe.")
        if row["status"] != "draft":
            raise ValueError("El análisis está cerrado y es de solo lectura.")

    @classmethod
    def _calculate(cls, scenario, rules, products, decisions, quote_prices):
        rule_map = {
            (row["product_type"], row["series"]):
                float(row["gross_margin_percent"])
            for row in rules
        }
        rail_bases = {}
        for product in products:
            product_type, series = cls._classification(product)
            length, rail_key = cls._rail_identity(product["internal_sku"])
            quote_rows = quote_prices.get(product["internal_sku"], [])
            quote_values = [float(row["accepted_fob_usd"]) for row in quote_rows]
            quote_base = (
                quote_values[-1]
                if quote_values and max(quote_values) - min(quote_values) <= .005
                else None
            )
            base_fob = quote_base or product.get("fob_usd")
            if product_type == "RIEL" and length == 3000 and base_fob:
                rail_bases[rail_key] = float(base_fob)

        lines = []
        for product in products:
            product_type, series = cls._classification(product)
            margin = rule_map.get(
                (product_type, series),
                rule_map.get((product_type, "GENERAL"), rule_map.get(("OTRO", "GENERAL"))),
            )
            erp_fob = (
                float(product["fob_usd"])
                if product.get("fob_usd") is not None else None
            )
            quote_rows = quote_prices.get(product["internal_sku"], [])
            quoted_values = [float(row["accepted_fob_usd"]) for row in quote_rows]
            quote_conflict = bool(quoted_values) and (
                max(quoted_values) - min(quoted_values) > .005
            )
            quote_fob = quoted_values[-1] if quoted_values and not quote_conflict else None
            quote_accepted_at = max(
                (str(row["accepted_at"]) for row in quote_rows), default=None
            )
            fob = (
                None if quote_conflict
                else quote_fob if quote_fob is not None else erp_fob
            )
            adjusted_fob = fob
            length, rail_key = cls._rail_identity(product["internal_sku"])
            rail_increment_applied = 0.0
            if product_type == "RIEL" and length in {1000, 2000} and rail_key in rail_bases:
                rail_increment_applied = float(scenario["rail_increment_percent"])
                adjusted_fob = (
                    rail_bases[rail_key] * length / 3000
                    * (1 + rail_increment_applied / 100)
                )
            calculated = None
            if adjusted_fob is not None and margin is not None and margin < 100:
                raw = (
                    adjusted_fob * float(scenario["import_factor"])
                    * float(scenario["trm"]) / (1 - margin / 100)
                )
                calculated = cls._round_price(raw, int(scenario["rounding_increment"]))
            current = (
                float(product["lista1_cop"])
                if product.get("lista1_cop") not in (None, 0) else None
            )
            variance = calculated - current if calculated is not None and current else None
            variance_percent = variance / current * 100 if variance is not None else None
            decision = decisions.get(product["internal_sku"])
            if (
                decision and quote_accepted_at
                and str(decision["decided_at"]) < quote_accepted_at
            ):
                decision = None
            lines.append({
                **product, "product_type": product_type, "series": series,
                "length_mm": length, "gross_margin_percent": margin,
                "erp_fob_usd": erp_fob, "quote_fob_usd": quote_fob,
                "quote_fob_conflict": quote_conflict,
                "quote_accepted_at": quote_accepted_at,
                "effective_fob_source": (
                    "vendor_quote" if quote_fob is not None else "erp"
                ),
                "adjusted_fob_usd": adjusted_fob,
                "rail_increment_applied": rail_increment_applied,
                "list_price_cop": current, "calculated_price_cop": calculated,
                "variance_amount": variance, "variance_percent": variance_percent,
                "current_sales_factor": (
                    current / erp_fob if current is not None and erp_fob else None
                ),
                "proposed_sales_factor": (
                    calculated / adjusted_fob
                    if calculated is not None and adjusted_fob else None
                ),
                "decision": decision,
            })
        return lines

    @staticmethod
    def _classification(product: dict[str, Any]) -> tuple[str, str]:
        sku = str(product["internal_sku"]).upper().strip()
        name = str(product.get("product_name") or "").upper()
        match = re.match(r"([A-Z]+)", sku)
        series = match.group(1) if match else "OTRO"
        if "RIEL" in name:
            product_type = "RIEL"
        elif "CHUMACERA" in name or re.match(r"^(BK|BF|FK|FF)\s?\d", sku):
            product_type = "CHUMACERA"
        elif "GRASA" in name:
            product_type = "GRASA"
        elif "RODAMIENTO" in name or "TUERCA LINEAL" in name:
            product_type = "RODAMIENTO"
        elif "GUIA LINEAL" in name or "CARRO" in name or "BLOQUE" in name:
            product_type = "BLOQUE"
        else:
            product_type = "OTRO"
        return product_type, series

    @staticmethod
    def _rail_identity(sku: str) -> tuple[int | None, str]:
        normalized = sku.upper().strip()
        match = re.search(r"([+-])(\d{3,4})L(?:M|Y)?(?=THK|$)", normalized)
        if not match:
            return None, normalized
        length = int(match.group(2))
        key = re.sub(
            r"([+-])\d{3,4}L(?:M|Y)?(?=THK|$)", "-LENGTH", normalized
        )
        return length, key

    @staticmethod
    def _round_price(value: float, increment: int) -> float:
        return float(math.floor(value / increment + .5) * increment)
