from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import json
import math
import re
from statistics import mean, median, pstdev
from typing import Any

from app.database.transaction import transaction


class StockForecastEngine:
    """Auditable per-SKU/branch demand and review engine."""

    VERSION = "stock-demand-v2-transfers-length"

    @classmethod
    def analyze(cls, snapshot_id: int) -> dict[str, Any]:
        with transaction(write=False) as connection:
            cached = connection.execute(
                """SELECT result_json FROM stock_planning_forecast_versions
                WHERE snapshot_id=? AND engine_version=?""",
                (snapshot_id, cls.VERSION),
            ).fetchone()
            if cached:
                return json.loads(cached["result_json"])
            header = connection.execute(
                """SELECT s.*,i.* FROM stock_planning_snapshots s
                JOIN stock_planning_analysis_inputs i ON i.snapshot_id=s.id
                WHERE s.id=?""", (snapshot_id,),
            ).fetchone()
            if not header:
                raise ValueError("El análisis no tiene horizonte configurado.")
            profile = connection.execute(
                "SELECT * FROM stock_planning_vendor_profiles WHERE id=?",
                (header["vendor_profile_id"],),
            ).fetchone()
            positions = connection.execute(
                """SELECT * FROM stock_planning_snapshot_inventory
                WHERE snapshot_id=?""", (snapshot_id,),
            ).fetchall()
            suffixes = json.loads(profile["sales_suffixes_json"])
            sales = cls._sales(connection, header["as_of_date"], suffixes)

        end = datetime.fromisoformat(header["as_of_date"]).date()
        values = cls._abc_values(sales, end)
        abc = cls._abc_classes(values)
        results = []
        for position in positions:
            key = (position["internal_sku"], str(position["branch_code"]))
            history = sales.get(key, [])
            monthly = cls._monthly(history, end, 36)
            model, forecast, mae = cls._choose(monthly)
            active = sum(value > 0 for value in monthly[-24:])
            avg = mean(monthly[-24:]) if monthly else 0
            variation = pstdev(monthly[-24:]) / avg if avg else 0
            xyz = "X" if active >= 18 and variation <= .5 else (
                "Y" if active >= 10 and variation <= 1 else "Z"
            )
            positive = [row for row in history if row[1] > 0]
            by_customer: dict[str, float] = defaultdict(float)
            for _, quantity, customer, _ in positive:
                by_customer[customer] += quantity
            sold = sum(by_customer.values())
            concentration = max(by_customer.values(), default=0) / sold if sold else 0
            lead_days = (
                header["manufacturing_days"] + header["international_shipping_days"]
                + header["receiving_days"]
                + (header["cali_transfer_days"] if str(position["branch_code"]) == "50" else 0)
            )
            horizon = lead_days / 30.4375 + header["coverage_months"]
            safety = min(mae * math.sqrt(max(horizon, 1)), 4 * forecast)
            target = math.ceil(forecast * horizon + safety)
            available = max(float(position["usable"]), 0) + float(
                position["undated_transit"] + position["dated_transit"]
            )
            order = max(0, math.ceil(target - available))
            reasons = []
            if position["usable"] < 0: reasons.append("Inventario utilizable negativo")
            if position["undated_transit"] > 0: reasons.append("Tránsito sin fecha")
            if sold > 0 and len(by_customer) <= 2: reasons.append("Pocos clientes")
            if concentration >= .70 and sold > 0: reasons.append("Demanda concentrada")
            if active <= 2 and sold > 0: reasons.append("Posible venta excepcional")
            if xyz == "Z" and order > 0: reasons.append("Demanda intermitente")
            if mae > max(forecast, 1): reasons.append("Baja precisión histórica")
            results.append({
                "sku": key[0], "branch": key[1], "abc": abc.get(key[0], "C"),
                "xyz": xyz, "model": model, "monthly_forecast": forecast,
                "backtest_mae": mae, "active_months_24": active,
                "sales_12": sum(monthly[-12:]), "sales_24": sum(monthly[-24:]),
                "sales_36": sum(monthly),
                "trend_12": cls._trend(monthly[-12:]),
                "customers_24": len(by_customer), "customer_concentration": concentration,
                "mean_24": avg, "median_24": median(monthly[-24:]),
                "max_month_24": max(monthly[-24:], default=0),
                "on_hand": position["on_hand"], "usable": position["usable"],
                "transit": position["undated_transit"] + position["dated_transit"],
                "lead_days": lead_days, "target_stock": target,
                "recommended_order": order, "review_reasons": reasons,
                "requires_review": bool(reasons),
            })
        transfers = cls._apply_transfers(results)
        results, transformations = cls._apply_length_transformations(results)
        packaged = cls._package(results, transfers, transformations)
        with transaction(write=True) as connection:
            connection.execute(
                """INSERT OR IGNORE INTO stock_planning_forecast_versions
                (snapshot_id,engine_version,result_json) VALUES (?,?,?)""",
                (snapshot_id, cls.VERSION, json.dumps(packaged, ensure_ascii=False)),
            )
            stored = connection.execute(
                """SELECT result_json FROM stock_planning_forecast_versions
                WHERE snapshot_id=? AND engine_version=?""",
                (snapshot_id, cls.VERSION),
            ).fetchone()
        return json.loads(stored["result_json"])

    @staticmethod
    def _sales(connection, through, suffixes):
        if not suffixes: return {}
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(raw_sales)").fetchall()
        }
        customer = "COALESCE(nit,'')" if "nit" in columns else "''"
        net = "COALESCE(neto,0)" if "neto" in columns else "0"
        marks = ",".join("?" for _ in suffixes)
        rows = connection.execute(
            f"""SELECT fecha,UPPER(TRIM(idproducto)) sku,TRIM(idbodega) branch,
                cantidad,{customer} customer,{net} neto
            FROM raw_sales WHERE fecha<=? AND UPPER(TRIM(sufijo)) IN ({marks})""",
            (through, *[str(x).upper() for x in suffixes]),
        ).fetchall()
        result = defaultdict(list)
        for row in rows:
            result[(row["sku"], row["branch"])].append(
                (row["fecha"], float(row["cantidad"] or 0), row["customer"], float(row["neto"] or 0))
            )
        return result

    @staticmethod
    def _monthly(history, end, count):
        totals = defaultdict(float)
        for raw_date, qty, *_ in history:
            when = datetime.fromisoformat(raw_date).date()
            totals[(when.year, when.month)] += qty
        result=[]
        year, month=end.year, end.month
        keys=[]
        for _ in range(count):
            keys.append((year,month)); month-=1
            if month==0: year-=1; month=12
        return [max(0,totals[key]) for key in reversed(keys)]

    @classmethod
    def _choose(cls, y):
        candidates={"Promedio 12":mean(y[-12:]),"Promedio 24":mean(y[-24:])}
        weights=range(1,13); candidates["Ponderado 12"]=sum(a*b for a,b in zip(y[-12:],weights))/sum(weights)
        scores={name:mean([abs(y[i]-cls._estimate(y[:i],name)) for i in range(24,len(y))]) for name in candidates}
        best=min(scores,key=scores.get)
        return best,max(0,candidates[best]),scores[best]

    @staticmethod
    def _estimate(y,name):
        if name=="Promedio 24": return mean(y[-24:])
        if name=="Promedio 12": return mean(y[-12:])
        w=range(1,min(12,len(y))+1); return sum(a*b for a,b in zip(y[-len(w):],w))/sum(w)

    @staticmethod
    def _abc_values(sales, end):
        result=defaultdict(float)
        start = end - timedelta(days=730)
        for (sku,_),rows in sales.items():
            result[sku] += sum(
                max(0, row[3]) for row in rows
                if datetime.fromisoformat(row[0]).date() >= start
            )
        return result

    @staticmethod
    def _trend(values):
        """Monthly least-squares slope, used as evidence rather than a forecast."""
        if len(values) < 2:
            return 0
        x_mean = (len(values) - 1) / 2
        y_mean = mean(values)
        denominator = sum((x - x_mean) ** 2 for x in range(len(values)))
        return sum(
            (x - x_mean) * (value - y_mean) for x, value in enumerate(values)
        ) / denominator if denominator else 0

    @staticmethod
    def _abc_classes(values):
        total=sum(values.values()) or 1; running=0; result={}
        for sku,value in sorted(values.items(),key=lambda x:x[1],reverse=True):
            running+=value; share=running/total
            result[sku]="A" if share<=.80 else ("B" if share<=.95 else "C")
        return result

    @staticmethod
    def _apply_transfers(rows):
        """Use genuine branch surplus before proposing an external purchase."""
        by_sku = defaultdict(dict)
        for row in rows:
            row["transfer_in"] = 0
            row["transfer_out"] = 0
            by_sku[row["sku"]][row["branch"]] = row
        transfers = []
        for sku, branches in by_sku.items():
            if "1" not in branches or "50" not in branches:
                continue
            for source_code, destination_code in (("1", "50"), ("50", "1")):
                source, destination = branches[source_code], branches[destination_code]
                source_supply = max(0, float(source["usable"]))
                source_surplus = math.floor(max(0, source_supply - source["target_stock"]))
                destination_deficit = int(destination["recommended_order"])
                quantity = min(source_surplus, destination_deficit)
                if quantity <= 0:
                    continue
                source["transfer_out"] += quantity
                destination["transfer_in"] += quantity
                destination["recommended_order"] -= quantity
                transfers.append({
                    "sku": sku, "from_branch": source_code,
                    "to_branch": destination_code, "quantity": quantity,
                    "avoided_purchase": quantity,
                })
        return transfers

    @classmethod
    def _apply_length_transformations(cls, rows):
        groups = defaultdict(list)
        for row in rows:
            parsed = cls._length_identity(row["sku"])
            if parsed:
                family, length, purchase_sku = parsed
                groups[(family, row["branch"], purchase_sku)].append((row, length))
        transformations = []
        for (family, branch, purchase_sku), components in groups.items():
            if not any(length != 3000 for _, length in components):
                continue
            required_mm = sum(
                int(row["recommended_order"]) * length for row, length in components
            )
            bars = math.ceil(required_mm / 3000) if required_mm else 0
            purchase_row = next(
                (row for row, length in components if length == 3000), None
            )
            if purchase_row is None:
                purchase_row = dict(components[0][0])
                purchase_row.update({
                    "sku": purchase_sku, "on_hand": 0, "usable": 0, "transit": 0,
                    "transfer_in": 0, "transfer_out": 0,
                    "model": "Conversión por longitud",
                })
                rows.append(purchase_row)
            component_detail = []
            component_reasons = []
            for row, length in components:
                units = int(row["recommended_order"])
                if units:
                    component_detail.append({
                        "sku": row["sku"], "units": units,
                        "length_mm": length, "required_mm": units * length,
                    })
                    component_reasons.extend(row["review_reasons"])
                if row is not purchase_row:
                    row["recommended_order"] = 0
                    row["covered_by_purchase_sku"] = purchase_sku
            purchase_row["recommended_order"] = bars
            purchase_row["target_stock"] = bars
            purchase_row["length_transformation"] = True
            purchase_row["length_family"] = family
            purchase_row["required_length_mm"] = required_mm
            purchase_row["component_demand"] = component_detail
            purchase_row["review_reasons"] = list(dict.fromkeys(component_reasons))
            purchase_row["requires_review"] = bool(purchase_row["review_reasons"])
            transformations.append({
                "family": family, "branch": branch,
                "purchase_sku": purchase_sku, "required_mm": required_mm,
                "bars": bars, "components": component_detail,
            })
        return rows, transformations

    @staticmethod
    def _length_identity(sku):
        """Recognize vendor-neutral rail and ball-screw length nomenclatures."""
        normalized = sku.upper().strip()
        rail = re.fullmatch(
            r"(?P<family>[A-Z]{2,6}\s+\d+[A-Z]*)-(?P<length>\d+)L(?P<suffix>[A-Z]+)",
            normalized,
        )
        screw = re.fullmatch(
            r"(?P<family>[A-Z]{2}\s+\d+)\+(?P<length>\d+)L(?P<suffix>[A-Z]+)",
            normalized,
        )
        match = rail or screw
        if not match:
            return None
        separator = "-" if rail else "+"
        family = match.group("family")
        return (
            family, int(match.group("length")),
            f"{family}{separator}3000L{match.group('suffix')}",
        )

    @staticmethod
    def _package(rows, transfers=None, transformations=None):
        categories=defaultdict(lambda:{"products":set(),"order_units":0,"review":0})
        for row in rows:
            item=categories[row["abc"]+row["xyz"]]; item["products"].add(row["sku"])
            item["order_units"]+=row["recommended_order"]; item["review"]+=row["requires_review"]
        return {"rows":rows,"review":[r for r in rows if r["requires_review"]],
                "automatic":[r for r in rows if not r["requires_review"]],
                "transfers": transfers or [],
                "transformations": transformations or [],
                "categories":[{"category":k,"products":len(v["products"]),"order_units":v["order_units"],"review":v["review"]} for k,v in sorted(categories.items())]}
