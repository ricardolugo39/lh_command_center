from __future__ import annotations

from typing import Any

from app.database.transaction import transaction
from app.workspace.stock_planning.forecasting import StockForecastEngine


class StockPlanningDecisionService:
    """Records human decisions without mutating forecast evidence."""

    @staticmethod
    def purchase_key(sku: str, branch: str) -> str:
        return f"{branch}|{sku.upper().strip()}"

    @staticmethod
    def transfer_key(sku: str, from_branch: str, to_branch: str) -> str:
        return f"{from_branch}|{to_branch}|{sku.upper().strip()}"

    @classmethod
    def save_purchase(
        cls, snapshot_id: int, sku: str, branch: str,
        approved_quantity: float, decided_by: str, note: str = "",
    ) -> None:
        forecast = StockForecastEngine.analyze(snapshot_id)
        row = next((item for item in forecast["rows"]
                    if item["sku"] == sku.upper().strip()
                    and item["branch"] == str(branch)), None)
        if not row or row["recommended_order"] <= 0:
            raise ValueError("La recomendación de compra no existe.")
        cls._save(
            snapshot_id=snapshot_id, item_type="purchase",
            item_key=cls.purchase_key(sku, branch), internal_sku=row["sku"],
            branch_code=str(branch), suggested=float(row["recommended_order"]),
            approved=approved_quantity, decided_by=decided_by, note=note,
        )

    @classmethod
    def save_transfer(
        cls, snapshot_id: int, sku: str, from_branch: str, to_branch: str,
        approved_quantity: float, decided_by: str, note: str = "",
    ) -> None:
        forecast = StockForecastEngine.analyze(snapshot_id)
        row = next((item for item in forecast.get("transfers", [])
                    if item["sku"] == sku.upper().strip()
                    and item["from_branch"] == str(from_branch)
                    and item["to_branch"] == str(to_branch)), None)
        if not row:
            raise ValueError("El traslado sugerido no existe.")
        cls._save(
            snapshot_id=snapshot_id, item_type="transfer",
            item_key=cls.transfer_key(sku, from_branch, to_branch),
            internal_sku=row["sku"], from_branch_code=str(from_branch),
            to_branch_code=str(to_branch), suggested=float(row["quantity"]),
            approved=approved_quantity, decided_by=decided_by, note=note,
        )

    @staticmethod
    def _save(**values: Any) -> None:
        approved = float(values["approved"])
        if approved < 0 or not approved.is_integer():
            raise ValueError("La cantidad final debe ser un entero mayor o igual a cero.")
        suggested = float(values["suggested"])
        status = "rejected" if approved == 0 else (
            "approved" if approved == suggested else "changed"
        )
        with transaction(write=True) as connection:
            connection.execute(
                """INSERT INTO stock_planning_decisions (
                    snapshot_id,item_type,item_key,internal_sku,branch_code,
                    from_branch_code,to_branch_code,suggested_quantity,
                    approved_quantity,decision_status,decision_note,decided_by
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(snapshot_id,item_type,item_key) DO UPDATE SET
                    approved_quantity=excluded.approved_quantity,
                    decision_status=excluded.decision_status,
                    decision_note=excluded.decision_note,
                    decided_by=excluded.decided_by,
                    decided_at=CURRENT_TIMESTAMP""",
                (values["snapshot_id"], values["item_type"], values["item_key"],
                 values["internal_sku"], values.get("branch_code"),
                 values.get("from_branch_code"), values.get("to_branch_code"),
                 suggested, approved, status, values.get("note") or None,
                 values["decided_by"]),
            )
            decision = connection.execute(
                """SELECT id FROM stock_planning_decisions
                WHERE snapshot_id=? AND item_type=? AND item_key=?""",
                (values["snapshot_id"], values["item_type"], values["item_key"]),
            ).fetchone()
            connection.execute(
                """INSERT INTO stock_planning_decision_history (
                    decision_id,snapshot_id,item_type,item_key,suggested_quantity,
                    approved_quantity,decision_status,decision_note,decided_by
                ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (decision["id"], values["snapshot_id"], values["item_type"],
                 values["item_key"], suggested, approved, status,
                 values.get("note") or None, values["decided_by"]),
            )

    @classmethod
    def approve_all_transfers(cls, snapshot_id: int, decided_by: str) -> int:
        forecast = StockForecastEngine.analyze(snapshot_id)
        count = 0
        for row in forecast.get("transfers", []):
            cls.save_transfer(
                snapshot_id, row["sku"], row["from_branch"], row["to_branch"],
                row["quantity"], decided_by,
            )
            count += 1
        return count

    @staticmethod
    def list(snapshot_id: int) -> list[dict[str, Any]]:
        with transaction(write=False) as connection:
            rows = connection.execute(
                """SELECT * FROM stock_planning_decisions
                WHERE snapshot_id=? ORDER BY item_type,item_key""", (snapshot_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @classmethod
    def present(cls, snapshot_id: int, forecast: dict[str, Any]) -> dict[str, Any]:
        decisions = {(d["item_type"], d["item_key"]): d for d in cls.list(snapshot_id)}
        with transaction(write=False) as connection:
            price_rows = connection.execute(
                """SELECT internal_sku,fob_usd
                FROM stock_planning_snapshot_fob_prices WHERE snapshot_id=?""",
                (snapshot_id,),
            ).fetchall()
        prices = {row["internal_sku"]: float(row["fob_usd"]) for row in price_rows}
        for row in forecast["rows"]:
            key = cls.purchase_key(row["sku"], row["branch"])
            decision = decisions.get(("purchase", key))
            row["decision"] = decision
            row["final_quantity"] = (
                decision["approved_quantity"] if decision
                else row["recommended_order"]
            )
            row["fob_usd"] = prices.get(row["sku"])
            row["total_fob_usd"] = (
                float(row["final_quantity"]) * row["fob_usd"]
                if row["fob_usd"] is not None else None
            )
        for row in forecast.get("transfers", []):
            key = cls.transfer_key(
                row["sku"], row["from_branch"], row["to_branch"]
            )
            decision = decisions.get(("transfer", key))
            row["decision"] = decision
            row["final_quantity"] = (
                decision["approved_quantity"] if decision else row["quantity"]
            )
        review = [row for row in forecast["rows"]
                  if row["recommended_order"] > 0 and row["requires_review"]]
        forecast["pending_purchase_count"] = sum(not row["decision"] for row in review)
        forecast["purchase_export_ready"] = forecast["pending_purchase_count"] == 0
        forecast["pending_transfer_count"] = sum(
            not row["decision"] for row in forecast.get("transfers", [])
        )
        forecast["transfer_export_ready"] = forecast["pending_transfer_count"] == 0
        purchase_rows = [
            row for row in forecast["rows"] if row["final_quantity"] > 0
        ]
        forecast["total_fob_usd"] = sum(
            row["total_fob_usd"] or 0 for row in purchase_rows
        )
        forecast["missing_fob_skus"] = sorted({
            row["sku"] for row in purchase_rows if row["fob_usd"] is None
        })
        forecast["missing_fob_count"] = len(forecast["missing_fob_skus"])
        forecast["fob_complete"] = forecast["missing_fob_count"] == 0
        return forecast
