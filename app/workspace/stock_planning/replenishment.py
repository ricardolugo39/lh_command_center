from __future__ import annotations

from datetime import date
from typing import Any

from app.database.transaction import transaction
from app.workspace.stock_planning.decisions import StockPlanningDecisionService
from app.workspace.stock_planning.forecasting import StockForecastEngine
from app.workspace.stock_planning.repository import StockPlanningRepository
from app.workspace.stock_planning.service import StockPlanningFoundationService


class StockReplenishmentService:
    """Quincenal transfer-first review for brands not ordered by the Cali manager."""

    PROFILE_CODES = ("SKF", "FAG", "NTN", "NQK", "KMK")
    RECIPIENT = "ricardo.lugo@lugohermanos.com"
    OWNERS = {"SKF": "Jean Pierre", "FAG": "Hernando Lugo", "NTN": "Hernando Lugo"}
    DEFAULT_COVERAGE_DAYS = 90
    TRANSFER_DAYS = 7

    @classmethod
    def run_due(
        cls, *, today: date | None = None, triggered_by: str = "scheduler",
        force: bool = False, profile_code: str | None = None,
        coverage_days: int | None = None,
    ) -> list[dict[str, Any]]:
        today = today or date.today()
        coverage_days = int(coverage_days or cls.DEFAULT_COVERAGE_DAYS)
        if not 30 <= coverage_days <= 365:
            raise ValueError("La cobertura debe estar entre 30 y 365 días.")
        if not force and today.day not in {1, 15}:
            return []
        requested_code = str(profile_code or "").strip().upper()
        if requested_code and requested_code not in cls.PROFILE_CODES:
            raise ValueError("La marca seleccionada no admite reabastecimiento de Cali.")
        results = []
        for profile in StockPlanningRepository.list_vendor_profiles():
            code = str(profile["profile_code"]).upper()
            if code not in cls.PROFILE_CODES or (requested_code and code != requested_code):
                continue
            results.append(cls._run_profile(
                profile, today, triggered_by, refresh=force,
                coverage_days=coverage_days,
            ))
        return results

    @classmethod
    def _run_profile(
        cls, profile, today, triggered_by, *, refresh=False,
        coverage_days=DEFAULT_COVERAGE_DAYS,
    ):
        run_date = today.isoformat()
        with transaction(write=True) as connection:
            existing = connection.execute(
                """SELECT * FROM stock_planning_replenishment_runs
                WHERE vendor_profile_id=? AND scheduled_for=?""",
                (profile["id"], run_date),
            ).fetchone()
            if existing and existing["status"] == "completed" and not refresh:
                return dict(existing)
            inventory_date = StockPlanningFoundationService._latest_inventory_date(
                connection, run_date, profile["inventory_brand_codes"]
            )
            previous = connection.execute(
                """SELECT inventory_snapshot_date
                FROM stock_planning_replenishment_runs
                WHERE vendor_profile_id=? AND status='completed'
                  AND scheduled_for<? ORDER BY scheduled_for DESC LIMIT 1""",
                (profile["id"], run_date),
            ).fetchone()
            missing = cls._missing_branches(
                connection, inventory_date, profile["inventory_brand_codes"]
            )
            stale = bool(not refresh and
                previous and inventory_date
                and previous["inventory_snapshot_date"] == inventory_date
            )
            status = "running" if inventory_date and not missing and not stale else "skipped"
            if stale:
                message = f"No hay inventario nuevo desde {inventory_date}."
            elif inventory_date and missing:
                message = "Inventario incompleto para bodegas: " + ", ".join(missing)
            elif not inventory_date:
                message = "No hay inventario disponible para la marca."
            else:
                message = None
            if existing:
                run_id = int(existing["id"])
                connection.execute(
                    "DELETE FROM stock_planning_notifications WHERE replenishment_run_id=?",
                    (run_id,),
                )
                connection.execute(
                    "DELETE FROM stock_planning_import_requests WHERE replenishment_run_id=?",
                    (run_id,),
                )
                connection.execute(
                    """UPDATE stock_planning_replenishment_runs SET
                    inventory_snapshot_date=?,snapshot_id=NULL,status=?,
                    triggered_by=?,message=?,completed_at=
                    CASE WHEN ?='skipped' THEN CURRENT_TIMESTAMP END WHERE id=?""",
                    (inventory_date, status, triggered_by, message, status, run_id),
                )
            else:
                cursor = connection.execute(
                    """INSERT INTO stock_planning_replenishment_runs (
                        vendor_profile_id,scheduled_for,inventory_snapshot_date,
                        status,triggered_by,message,completed_at
                    ) VALUES (?,?,?,?,?,?,CASE WHEN ?='skipped' THEN CURRENT_TIMESTAMP END)""",
                    (
                        profile["id"], run_date, inventory_date, status,
                        triggered_by, message, status,
                    ),
                )
                run_id = int(cursor.lastrowid)
            if status == "skipped":
                cls._notify(connection, run_id, None, profile["vendor_name"], message)
                return {"id": run_id, "status": status, "message": message}

        try:
            snapshot = StockPlanningFoundationService.create_snapshot(
                profile_id=profile["id"], as_of_date=today,
                created_by=triggered_by,
                assumptions=cls._assumptions(coverage_days),
            )
            forecast = StockForecastEngine.analyze(snapshot.snapshot_id)
            rows = {(row["sku"], row["branch"]): row for row in forecast["rows"]}
            automatic = 0
            pending = 0
            review_candidates = []
            ignored = []
            for transfer in forecast.get("transfers", []):
                if not cls._to_cali(transfer):
                    ignored.append(transfer)
                    continue
                destination = rows.get((transfer["sku"], transfer["to_branch"]), {})
                if cls._automatic(destination):
                    cls._record_transfer(
                        snapshot.snapshot_id, transfer, transfer["quantity"],
                        "Aprobación automática por frecuencia en Cali; Bogotá conserva su cobertura.",
                    )
                    automatic += 1
                elif cls._eligible(destination):
                    review_candidates.append((transfer, destination))
                else:
                    ignored.append(transfer)
            review_candidates.sort(key=lambda item: (
                -int(item[1].get("active_months_24") or 0),
                -float(item[1].get("sales_12") or 0),
                -float(item[0].get("quantity") or 0),
            ))
            pending = len(review_candidates)
            for transfer in ignored:
                cls._record_transfer(
                    snapshot.snapshot_id, transfer, 0,
                    "Sin acción: menos de tres meses con venta en los últimos 24 o sin venta reciente en Cali.",
                )
            requests = cls._create_import_requests(
                run_id, snapshot.snapshot_id, profile, forecast
            )
            message = (
                f"{automatic} traslado(s) aprobados automáticamente, "
                f"{pending} traslado(s) por revisar y "
                f"{requests} faltante(s) que Bogotá no puede cubrir."
            )
            with transaction(write=True) as connection:
                connection.execute(
                    """UPDATE stock_planning_replenishment_runs
                    SET snapshot_id=?,status='completed',message=?,
                        completed_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (snapshot.snapshot_id, message, run_id),
                )
                if automatic or pending or requests:
                    cls._notify(
                        connection, run_id, snapshot.snapshot_id,
                        profile["vendor_name"], message,
                    )
            return {"id": run_id, "status": "completed", "message": message}
        except Exception as error:
            with transaction(write=True) as connection:
                connection.execute(
                    """UPDATE stock_planning_replenishment_runs
                    SET status='failed',message=?,completed_at=CURRENT_TIMESTAMP
                    WHERE id=?""", (str(error), run_id),
                )
            return {"id": run_id, "status": "failed", "message": str(error)}

    @classmethod
    def _automatic(cls, row):
        critical = {"Inventario utilizable negativo", "Tránsito sin fecha"}
        return (
            int(row.get("active_months_24") or 0) >= 6
            and float(row.get("sales_12") or 0) > 0
            and not critical.intersection(row.get("review_reasons") or [])
        )

    @staticmethod
    def _eligible(row):
        return (
            int(row.get("active_months_24") or 0) >= 3
            and float(row.get("sales_12") or 0) > 0
        )

    @staticmethod
    def _to_cali(transfer):
        return (
            str(transfer.get("from_branch")) == "1"
            and str(transfer.get("to_branch")) == "50"
        )

    @classmethod
    def _assumptions(cls, coverage_days):
        return {
            "manufacturing_days": 0,
            "international_shipping_days": 0,
            "receiving_days": 0,
            "cali_transfer_days": cls.TRANSFER_DAYS,
            # The forecast adds transfer days for Cali. Subtract them here so
            # the requested input remains the total Cali coverage horizon.
            "coverage_months": max(
                float(coverage_days) - cls.TRANSFER_DAYS, 1
            ) / 30.4375,
        }

    @staticmethod
    def _record_transfer(snapshot_id, transfer, approved, note):
        StockPlanningDecisionService._save(
            snapshot_id=snapshot_id, item_type="transfer",
            item_key=StockPlanningDecisionService.transfer_key(
                transfer["sku"], transfer["from_branch"], transfer["to_branch"]
            ),
            internal_sku=transfer["sku"],
            from_branch_code=transfer["from_branch"],
            to_branch_code=transfer["to_branch"],
            suggested=float(transfer["quantity"]), approved=approved,
            decided_by="sistema-quincenal", note=note,
        )

    @classmethod
    def reconcile_completed_runs(cls) -> list[dict[str, Any]]:
        """Apply the capped-attention policy to already-created initial runs."""
        with transaction(write=False) as connection:
            runs = [dict(row) for row in connection.execute(
                """SELECT r.*,v.profile_code,v.vendor_name
                FROM stock_planning_replenishment_runs r
                JOIN stock_planning_vendor_profiles v ON v.id=r.vendor_profile_id
                WHERE r.status='completed' AND r.snapshot_id IS NOT NULL"""
            ).fetchall()]
        results = []
        for run in runs:
            forecast = StockForecastEngine.analyze(run["snapshot_id"])
            rows = {(row["sku"], row["branch"]): row for row in forecast["rows"]}
            automatic, candidates, ignored = 0, [], []
            for transfer in forecast.get("transfers", []):
                if not cls._to_cali(transfer):
                    ignored.append(transfer)
                    continue
                destination = rows.get((transfer["sku"], transfer["to_branch"]), {})
                if cls._automatic(destination):
                    cls._record_transfer(
                        run["snapshot_id"], transfer, transfer["quantity"],
                        "Aprobación automática por frecuencia en Cali; Bogotá conserva su cobertura.",
                    )
                    automatic += 1
                elif cls._eligible(destination):
                    candidates.append((transfer, destination))
                else:
                    ignored.append(transfer)
            candidates.sort(key=lambda item: (
                -int(item[1].get("active_months_24") or 0),
                -float(item[1].get("sales_12") or 0),
                -float(item[0].get("quantity") or 0),
            ))
            with transaction(write=True) as connection:
                connection.execute(
                    "DELETE FROM stock_planning_import_requests WHERE replenishment_run_id=?",
                    (run["id"],),
                )
            for transfer in ignored:
                cls._record_transfer(
                    run["snapshot_id"], transfer, 0,
                    "Sin acción: menos de tres meses con venta en los últimos 24 o sin venta reciente en Cali.",
                )
            request_count = cls._create_import_requests(
                run["id"], run["snapshot_id"], {
                    "id": run["vendor_profile_id"],
                    "profile_code": run["profile_code"],
                }, forecast,
            )
            pending = len(candidates)
            message = (
                f"{automatic} traslado(s) automáticos, {pending} traslado(s) "
                f"por revisar y {request_count} faltante(s) que Bogotá no puede cubrir."
            )
            with transaction(write=True) as connection:
                connection.execute(
                    "UPDATE stock_planning_replenishment_runs SET message=? WHERE id=?",
                    (message, run["id"]),
                )
                connection.execute(
                    "UPDATE stock_planning_notifications SET message=? WHERE replenishment_run_id=?",
                    (message, run["id"]),
                )
            results.append({"brand": run["profile_code"], "message": message})
        return results

    @classmethod
    def _create_import_requests(cls, run_id, snapshot_id, profile, forecast):
        owner = cls.OWNERS.get(str(profile["profile_code"]).upper())
        count = 0
        candidates = [
            row for row in forecast["rows"]
            if row["branch"] == "50" and row["recommended_order"] > 0
            and cls._eligible(row)
        ]
        candidates.sort(key=lambda row: (
            0 if cls._automatic(row) else 1,
            0 if row["abc"] == "A" else 1,
            -float(row.get("sales_12") or 0),
            -float(row["recommended_order"]),
        ))
        with transaction(write=True) as connection:
            for row in candidates:
                status = "ready" if cls._automatic(row) else "pending_review"
                connection.execute(
                    """INSERT OR IGNORE INTO stock_planning_import_requests (
                        replenishment_run_id,snapshot_id,vendor_profile_id,
                        internal_sku,branch_code,suggested_quantity,abc_class,
                        xyz_class,assigned_to,status,reason
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        run_id, snapshot_id, profile["id"], row["sku"], "50",
                        row["recommended_order"], row["abc"], row["xyz"], owner,
                        status,
                        "Bogotá no puede abastecer el faltante sin bajar de su cobertura protegida.",
                    ),
                )
                count += 1
        return count

    @staticmethod
    def _missing_branches(connection, inventory_date, brands):
        if not inventory_date:
            return ["1", "16", "50"]
        found = {
            str(row["branch_code"])
            for row in connection.execute(
                """SELECT DISTINCT TRIM(idbodega) branch_code
                FROM inventario_snapshot WHERE fecha_snapshot=?
                  AND TRIM(idbodega) IN ('1','16','50')""",
                (inventory_date,),
            ).fetchall()
        }
        return [code for code in ("1", "16", "50") if code not in found]

    @classmethod
    def _notify(cls, connection, run_id, snapshot_id, brand, message):
        connection.execute(
            """INSERT INTO stock_planning_notifications (
                replenishment_run_id,recipient_email,title,message,snapshot_id
            ) VALUES (?,?,?,?,?)""",
            (run_id, cls.RECIPIENT, f"Reabastecimiento {brand}", message, snapshot_id),
        )

    @classmethod
    def inbox(cls):
        with transaction(write=False) as connection:
            notifications = [dict(row) for row in connection.execute(
                """SELECT n.*,v.vendor_name FROM stock_planning_notifications n
                JOIN stock_planning_replenishment_runs r ON r.id=n.replenishment_run_id
                JOIN stock_planning_vendor_profiles v ON v.id=r.vendor_profile_id
                WHERE n.recipient_email=? ORDER BY n.created_at DESC LIMIT 30""",
                (cls.RECIPIENT,),
            ).fetchall()]
            requests = [dict(row) for row in connection.execute(
                """SELECT q.*,v.vendor_name FROM stock_planning_import_requests q
                JOIN stock_planning_vendor_profiles v ON v.id=q.vendor_profile_id
                WHERE q.status IN ('ready','pending_review')
                ORDER BY q.created_at DESC,q.id DESC LIMIT 100"""
            ).fetchall()]
        return {
            "notifications": notifications,
            "unread_count": sum(not item["read_at"] for item in notifications),
            "import_requests": requests,
        }

    @classmethod
    def report(cls, snapshot_id: int) -> dict[str, Any]:
        """Present a replenishment snapshot as transfers, never as an order."""
        forecast = StockPlanningDecisionService.present(
            snapshot_id, StockForecastEngine.analyze(snapshot_id)
        )
        positions = {
            (row["sku"], row["branch"]): row for row in forecast["rows"]
        }
        automatic, review, approved = [], [], []
        for transfer in forecast.get("transfers", []):
            if transfer["from_branch"] != "1" or transfer["to_branch"] != "50":
                continue
            decision = transfer.get("decision")
            if decision and float(decision["approved_quantity"]) <= 0:
                continue
            cali = positions.get((transfer["sku"], "50"), {})
            bogota = positions.get((transfer["sku"], "1"), {})
            item = {
                **transfer,
                "class_code": f"{cali.get('abc', '')}{cali.get('xyz', '')}",
                "active_months_24": int(cali.get("active_months_24") or 0),
                "cali_sales_12": cali.get("sales_12", 0),
                "cali_monthly_demand": cali.get("monthly_forecast", 0),
                "cali_target": cali.get("target_stock", 0),
                "bogota_monthly_demand": bogota.get("monthly_forecast", 0),
                "bogota_target": bogota.get("target_stock", 0),
                "bogota_surplus": max(
                    0, float(bogota.get("usable", 0))
                    - float(bogota.get("target_stock", 0))
                ),
                "review_reasons": cali.get("review_reasons", []),
            }
            if not decision:
                review.append(item)
            elif decision.get("decided_by") == "sistema-quincenal":
                automatic.append(item)
            else:
                approved.append(item)
        with transaction(write=False) as connection:
            requests = [dict(row) for row in connection.execute(
                """SELECT q.*,v.vendor_name
                FROM stock_planning_import_requests q
                JOIN stock_planning_vendor_profiles v ON v.id=q.vendor_profile_id
                WHERE q.snapshot_id=? AND q.status IN ('ready','pending_review')
                ORDER BY q.suggested_quantity DESC,q.internal_sku""",
                (snapshot_id,),
            ).fetchall()]
            inputs = connection.execute(
                """SELECT cali_transfer_days,coverage_months
                FROM stock_planning_analysis_inputs WHERE snapshot_id=?""",
                (snapshot_id,),
            ).fetchone()
        for request_row in requests:
            cali = positions.get((request_row["internal_sku"], "50"), {})
            bogota = positions.get((request_row["internal_sku"], "1"), {})
            request_row.update({
                "active_months_24": int(cali.get("active_months_24") or 0),
                "sales_12": float(cali.get("sales_12") or 0),
                "cali_inventory": float(cali.get("usable") or 0),
                "cali_transit": float(cali.get("transit") or 0),
                "bogota_inventory": float(bogota.get("usable") or 0),
            })
        return {
            "automatic": automatic,
            "review": review,
            "approved": approved,
            "uncovered": requests,
            "coverage_days": round(
                float(inputs["coverage_months"]) * 30.4375
                + float(inputs["cali_transfer_days"])
            ),
        }
