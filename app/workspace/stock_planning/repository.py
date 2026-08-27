from __future__ import annotations

import json
from sqlite3 import Connection
from typing import Any, Iterable

from app.database.transaction import connection_scope


class StockPlanningRepository:
    """Persistence and source discovery for stock-planning master data."""

    @staticmethod
    def create_vendor_profile(values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO stock_planning_vendor_profiles (
                    vendor_name, profile_code, inventory_brand_codes_json,
                    sales_suffixes_json, default_manufacturing_days,
                    default_shipping_days, default_receiving_days,
                    default_cali_transfer_days, lead_time_day_basis
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    values["vendor_name"], values["profile_code"],
                    json.dumps(values.get("inventory_brand_codes", [])),
                    json.dumps(values.get("sales_suffixes", [])),
                    values.get("default_manufacturing_days"),
                    values.get("default_shipping_days"),
                    values.get("default_receiving_days"),
                    values.get("default_cali_transfer_days"),
                    values.get("lead_time_day_basis", "calendar"),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def get_vendor_profile(profile_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM stock_planning_vendor_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["inventory_brand_codes"] = json.loads(
            result.pop("inventory_brand_codes_json") or "[]"
        )
        result["sales_suffixes"] = json.loads(
            result.pop("sales_suffixes_json") or "[]"
        )
        return result

    @staticmethod
    def list_vendor_profiles() -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM stock_planning_vendor_profiles
                ORDER BY is_active DESC,vendor_name"""
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["inventory_brand_codes"] = json.loads(
                item.pop("inventory_brand_codes_json") or "[]"
            )
            item["sales_suffixes"] = json.loads(
                item.pop("sales_suffixes_json") or "[]"
            )
            result.append(item)
        return result

    @staticmethod
    def list_branches() -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM stock_planning_branches
                ORDER BY is_active DESC,branch_code"""
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_catalog(profile_id: int | None = None) -> list[dict[str, Any]]:
        parameters: tuple[Any, ...] = ()
        where = ""
        if profile_id:
            where = "WHERE c.vendor_profile_id=?"
            parameters = (profile_id,)
        with connection_scope() as connection:
            rows = connection.execute(
                f"""SELECT c.*,v.vendor_name FROM stock_planning_product_catalog c
                JOIN stock_planning_vendor_profiles v ON v.id=c.vendor_profile_id
                {where} ORDER BY v.vendor_name,c.internal_sku""", parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_families(profile_id: int | None = None) -> list[dict[str, Any]]:
        parameters: tuple[Any, ...] = ()
        where = ""
        if profile_id:
            where = "WHERE f.vendor_profile_id=?"
            parameters = (profile_id,)
        with connection_scope() as connection:
            rows = connection.execute(
                f"""SELECT f.*,v.vendor_name,COUNT(m.internal_sku) AS member_count
                FROM stock_planning_families f
                JOIN stock_planning_vendor_profiles v ON v.id=f.vendor_profile_id
                LEFT JOIN stock_planning_family_members m ON m.family_id=f.id
                {where} GROUP BY f.id ORDER BY v.vendor_name,f.family_name""",
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_transformations(profile_id: int | None = None) -> list[dict[str, Any]]:
        parameters: tuple[Any, ...] = ()
        where = ""
        if profile_id:
            where = "WHERE t.vendor_profile_id=?"
            parameters = (profile_id,)
        with connection_scope() as connection:
            rows = connection.execute(
                f"""SELECT t.*,v.vendor_name,COUNT(i.sales_sku) AS input_count
                FROM stock_planning_transformations t
                JOIN stock_planning_vendor_profiles v ON v.id=t.vendor_profile_id
                LEFT JOIN stock_planning_transformation_inputs i
                    ON i.transformation_id=t.id
                {where} GROUP BY t.id
                ORDER BY v.vendor_name,t.transformation_code,t.version DESC""",
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_transit(profile_id: int | None = None) -> list[dict[str, Any]]:
        parameters: tuple[Any, ...] = ()
        where = ""
        if profile_id:
            where = "WHERE t.vendor_profile_id=?"
            parameters = (profile_id,)
        with connection_scope() as connection:
            rows = connection.execute(
                f"""SELECT t.*,v.vendor_name,b.branch_name
                FROM stock_planning_transit_supplies t
                JOIN stock_planning_vendor_profiles v ON v.id=t.vendor_profile_id
                LEFT JOIN stock_planning_branches b ON b.branch_code=t.branch_code
                {where} ORDER BY t.expected_date IS NULL,t.expected_date,t.id""",
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_snapshots(profile_id: int | None = None) -> list[dict[str, Any]]:
        parameters: tuple[Any, ...] = ()
        where = ""
        if profile_id:
            where = "WHERE s.vendor_profile_id=?"
            parameters = (profile_id,)
        with connection_scope() as connection:
            rows = connection.execute(
                f"""SELECT s.*,v.vendor_name,
                    (SELECT COUNT(*) FROM stock_planning_snapshot_products p
                     WHERE p.snapshot_id=s.id) AS product_count,
                    (SELECT COUNT(*) FROM stock_planning_snapshot_issues i
                     WHERE i.snapshot_id=s.id
                       AND i.issue_code <> 'PRODUCT_NOT_IN_CATALOG') AS issue_count
                FROM stock_planning_snapshots s
                JOIN stock_planning_vendor_profiles v ON v.id=s.vendor_profile_id
                {where} ORDER BY s.created_at DESC,s.id DESC""", parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def snapshot_detail(snapshot_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            header = connection.execute(
                """SELECT s.*,v.vendor_name FROM stock_planning_snapshots s
                JOIN stock_planning_vendor_profiles v ON v.id=s.vendor_profile_id
                WHERE s.id=?""", (snapshot_id,),
            ).fetchone()
            if not header:
                return None
            products = connection.execute(
                """SELECT * FROM stock_planning_snapshot_products
                WHERE snapshot_id=? ORDER BY internal_sku""", (snapshot_id,),
            ).fetchall()
            inventory = connection.execute(
                """SELECT * FROM stock_planning_snapshot_inventory
                WHERE snapshot_id=? ORDER BY branch_code,internal_sku""",
                (snapshot_id,),
            ).fetchall()
            transit = connection.execute(
                """SELECT * FROM stock_planning_snapshot_transit
                WHERE snapshot_id=? ORDER BY expected_date,branch_code,internal_sku""",
                (snapshot_id,),
            ).fetchall()
            issues = connection.execute(
                """SELECT * FROM stock_planning_snapshot_issues
                WHERE snapshot_id=? AND issue_code <> 'PRODUCT_NOT_IN_CATALOG'
                ORDER BY CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END,
                    issue_code,branch_code,internal_sku""", (snapshot_id,),
            ).fetchall()
            inputs = connection.execute(
                """SELECT * FROM stock_planning_analysis_inputs
                WHERE snapshot_id=?""", (snapshot_id,),
            ).fetchone()
        return {
            "snapshot": dict(header),
            "products": [dict(row) for row in products],
            "inventory": [dict(row) for row in inventory],
            "transit": [dict(row) for row in transit],
            "issues": [dict(row) for row in issues],
            "inputs": dict(inputs) if inputs else None,
        }

    @staticmethod
    def upsert_catalog_product(profile_id: int, values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO stock_planning_product_catalog (
                    vendor_profile_id, internal_sku, vendor_sku, product_name,
                    purchase_uom, units_per_pack, is_active, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vendor_profile_id, internal_sku) DO UPDATE SET
                    vendor_sku=excluded.vendor_sku,
                    product_name=excluded.product_name,
                    purchase_uom=excluded.purchase_uom,
                    units_per_pack=excluded.units_per_pack,
                    is_active=excluded.is_active,
                    source=excluded.source,
                    updated_at=CURRENT_TIMESTAMP""",
                (
                    profile_id, values["internal_sku"], values.get("vendor_sku"),
                    values.get("product_name"), values.get("purchase_uom"),
                    values.get("units_per_pack"), values.get("is_active", 1),
                    values.get("source", "manual"),
                ),
            )
            row = connection.execute(
                """SELECT id FROM stock_planning_product_catalog
                WHERE vendor_profile_id=? AND internal_sku=?""",
                (profile_id, values["internal_sku"]),
            ).fetchone()
            return int(row["id"])

    @staticmethod
    def upsert_branch(values: dict[str, Any]) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO stock_planning_branches (
                    branch_code,branch_name,is_primary_receipt,is_active
                ) VALUES (?,?,?,?)
                ON CONFLICT(branch_code) DO UPDATE SET
                    branch_name=excluded.branch_name,
                    is_primary_receipt=excluded.is_primary_receipt,
                    is_active=excluded.is_active,
                    updated_at=CURRENT_TIMESTAMP""",
                (values["branch_code"], values["branch_name"],
                 values.get("is_primary_receipt", 0), values.get("is_active", 1)),
            )

    @staticmethod
    def add_transit_supply(profile_id: int, values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO stock_planning_transit_supplies (
                    vendor_profile_id, branch_code, internal_sku, quantity,
                    expected_date, purchase_order_reference, transit_status,
                    source, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile_id, values["branch_code"], values["internal_sku"],
                    values["quantity"], values.get("expected_date"),
                    values.get("purchase_order_reference"),
                    values.get("transit_status", "confirmed"),
                    values.get("source", "manual"),
                    values.get("created_by", "system"),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def upsert_family(profile_id: int, values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO stock_planning_families (
                    vendor_profile_id,family_code,family_name,source,is_active
                ) VALUES (?,?,?,?,?)
                ON CONFLICT(vendor_profile_id,family_code) DO UPDATE SET
                    family_name=excluded.family_name,
                    source=excluded.source,
                    is_active=excluded.is_active,
                    updated_at=CURRENT_TIMESTAMP""",
                (profile_id, values["family_code"], values["family_name"],
                 values.get("source", "derived"), values.get("is_active", 1)),
            )
            row = connection.execute(
                """SELECT id FROM stock_planning_families
                WHERE vendor_profile_id=? AND family_code=?""",
                (profile_id, values["family_code"]),
            ).fetchone()
            return int(row["id"])

    @staticmethod
    def upsert_family_member(family_id: int, values: dict[str, Any]) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO stock_planning_family_members (
                    family_id,internal_sku,relationship_role,confidence,source,
                    reviewed_by,reviewed_at
                ) VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(family_id,internal_sku,relationship_role) DO UPDATE SET
                    confidence=excluded.confidence,source=excluded.source,
                    reviewed_by=excluded.reviewed_by,reviewed_at=excluded.reviewed_at""",
                (family_id, values["internal_sku"],
                 values.get("relationship_role", "member"),
                 values.get("confidence"), values.get("source", "derived"),
                 values.get("reviewed_by"), values.get("reviewed_at")),
            )

    @staticmethod
    def create_transformation(profile_id: int, values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO stock_planning_transformations (
                    vendor_profile_id,transformation_code,transformation_type,
                    purchase_sku,purchase_quantity,waste_rate,rounding_mode,
                    version,status,effective_from,effective_to,notes,created_by,
                    approved_by,approved_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (profile_id, values["transformation_code"],
                 values["transformation_type"], values["purchase_sku"],
                 values.get("purchase_quantity", 1), values.get("waste_rate", 0),
                 values.get("rounding_mode", "ceil"), values.get("version", 1),
                 values.get("status", "draft"), values.get("effective_from"),
                 values.get("effective_to"), values.get("notes"),
                 values.get("created_by", "system"), values.get("approved_by"),
                 values.get("approved_at")),
            )
            transformation_id = int(cursor.lastrowid)
            connection.executemany(
                """INSERT INTO stock_planning_transformation_inputs (
                    transformation_id,sales_sku,sales_quantity,normalized_consumption
                ) VALUES (?,?,?,?)""",
                [(transformation_id, item["sales_sku"],
                  item.get("sales_quantity", 1), item["normalized_consumption"])
                 for item in values.get("inputs", [])],
            )
            return transformation_id

    @staticmethod
    def table_columns(connection: Connection, table_name: str) -> set[str]:
        return {
            row["name"]
            for row in connection.execute(
                f"PRAGMA table_info({table_name})"
            ).fetchall()
        }

    @staticmethod
    def table_exists(connection: Connection, table_name: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone() is not None

    @staticmethod
    def insert_many(
        connection: Connection,
        sql: str,
        rows: Iterable[tuple[Any, ...]],
    ) -> None:
        connection.executemany(sql, list(rows))
