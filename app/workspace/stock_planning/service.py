from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from typing import Any
from uuid import uuid4

from app.database.transaction import transaction, transactional
from app.workspace.stock_planning.repository import StockPlanningRepository


@dataclass(frozen=True)
class FrozenPlanningSnapshot:
    snapshot_id: int
    snapshot_key: str
    product_count: int
    inventory_row_count: int
    issue_count: int
    inventory_snapshot_date: str | None
    sales_through_date: str | None


class StockPlanningFoundationService:
    """Creates auditable source snapshots; it does not forecast or recommend."""

    @staticmethod
    @transactional
    def create_vendor_profile(**values: Any) -> int:
        values["profile_code"] = _required_code(values.get("profile_code"))
        values["vendor_name"] = _required_text(values.get("vendor_name"))
        return StockPlanningRepository.create_vendor_profile(values)

    @staticmethod
    def dashboard(profile_id: int | None = None) -> dict[str, Any]:
        profiles = StockPlanningRepository.list_vendor_profiles()
        selected = profile_id or (profiles[0]["id"] if profiles else None)
        profile = next((item for item in profiles if item["id"] == selected), None)
        source_status = {
            "inventory_date": None, "sales_date": None, "product_count": 0,
            "inventory_product_count": 0, "sales_product_count": 0,
            "transit_units": 0,
        }
        if profile:
            today = date.today().isoformat()
            with transaction(write=False) as connection:
                branches = StockPlanningFoundationService._active_branches(connection)
                inventory_date = StockPlanningFoundationService._latest_inventory_date(
                    connection, today, profile["inventory_brand_codes"]
                )
                inventory = StockPlanningFoundationService._inventory_rows(
                    connection, inventory_date, profile["inventory_brand_codes"],
                    [branch["branch_code"] for branch in branches],
                )
                sales, sales_date = StockPlanningFoundationService._sales_products(
                    connection, today, profile["sales_suffixes"]
                )
                source_status = {
                    "inventory_date": inventory_date, "sales_date": sales_date,
                    "product_count": len({
                        row["internal_sku"] for row in inventory + sales
                    }),
                    "inventory_product_count": len({
                        row["internal_sku"] for row in inventory
                    }),
                    "sales_product_count": len({
                        row["internal_sku"] for row in sales
                    }),
                    "transit_units": sum(
                        float(row["undated_transit"] or 0) for row in inventory
                    ),
                }
        return {
            "profiles": profiles,
            "selected_profile": profile,
            "selected_profile_id": selected,
            # History is global: changing the planning brand must never make
            # previously saved analyses appear to have disappeared.
            "snapshots": StockPlanningRepository.list_snapshots(),
            "source_status": source_status,
            "today": date.today().isoformat(),
        }

    @staticmethod
    @transactional
    def register_catalog_product(
        profile_id: int,
        **values: Any,
    ) -> int:
        values["internal_sku"] = _required_sku(values.get("internal_sku"))
        if values.get("vendor_sku"):
            values["vendor_sku"] = _required_sku(values["vendor_sku"])
        return StockPlanningRepository.upsert_catalog_product(profile_id, values)

    @staticmethod
    @transactional
    def register_branch(**values: Any) -> None:
        values["branch_code"] = _required_text(values.get("branch_code"))
        values["branch_name"] = _required_text(values.get("branch_name"))
        StockPlanningRepository.upsert_branch(values)

    @staticmethod
    @transactional
    def register_transit_supply(
        profile_id: int,
        **values: Any,
    ) -> int:
        values["branch_code"] = _required_text(values.get("branch_code"))
        values["internal_sku"] = _required_sku(values.get("internal_sku"))
        quantity = float(values.get("quantity", 0))
        if quantity < 0:
            raise ValueError("Transit quantity cannot be negative.")
        values["quantity"] = quantity
        return StockPlanningRepository.add_transit_supply(profile_id, values)

    @staticmethod
    @transactional
    def register_family(profile_id: int, **values: Any) -> int:
        values["family_code"] = _required_code(values.get("family_code"))
        values["family_name"] = _required_text(values.get("family_name"))
        return StockPlanningRepository.upsert_family(profile_id, values)

    @staticmethod
    @transactional
    def register_family_member(family_id: int, **values: Any) -> None:
        values["internal_sku"] = _required_sku(values.get("internal_sku"))
        StockPlanningRepository.upsert_family_member(family_id, values)

    @staticmethod
    @transactional
    def register_transformation(profile_id: int, **values: Any) -> int:
        values["transformation_code"] = _required_code(
            values.get("transformation_code")
        )
        values["purchase_sku"] = _required_sku(values.get("purchase_sku"))
        if values.get("transformation_type") not in {
            "unit_conversion", "length_cut", "pack", "substitute", "assembly",
        }:
            raise ValueError("Unsupported transformation type.")
        inputs = []
        for item in values.get("inputs", []):
            normalized = float(item.get("normalized_consumption", 0))
            if normalized <= 0:
                raise ValueError("normalized_consumption must be positive.")
            inputs.append({
                **item,
                "sales_sku": _required_sku(item.get("sales_sku")),
                "normalized_consumption": normalized,
            })
        if not inputs:
            raise ValueError("A transformation requires at least one sales SKU.")
        values["inputs"] = inputs
        return StockPlanningRepository.create_transformation(profile_id, values)

    @classmethod
    def create_snapshot(
        cls,
        *,
        profile_id: int,
        as_of_date: str | date,
        created_by: str,
        assumptions: dict[str, Any] | None = None,
    ) -> FrozenPlanningSnapshot:
        as_of = as_of_date.isoformat() if isinstance(as_of_date, date) else str(as_of_date)
        if not created_by.strip():
            raise ValueError("created_by is required.")
        with transaction(write=True) as connection:
            profile = StockPlanningRepository.get_vendor_profile(profile_id)
            if not profile or not profile["is_active"]:
                raise ValueError("Active vendor profile not found.")

            inventory_date = cls._latest_inventory_date(
                connection, as_of, profile["inventory_brand_codes"]
            )
            planning_branches = cls._active_branches(connection)
            inventory = cls._inventory_rows(
                connection, inventory_date, profile["inventory_brand_codes"],
                [branch["branch_code"] for branch in planning_branches],
            )
            sales, sales_through = cls._sales_products(
                connection, as_of, profile["sales_suffixes"]
            )
            sales_evidence = cls._sales_evidence(
                connection, as_of, profile["sales_suffixes"]
            )
            catalog = cls._catalog_products(connection, profile_id)
            transit = cls._transit_rows(connection, profile_id, as_of)
            related = cls._relationship_products(connection, profile_id)
            products = cls._build_universe(catalog, inventory, sales, transit, related)
            fob_prices = cls._fob_prices(connection, profile, products)
            inventory = cls._complete_branch_positions(
                planning_branches, products, inventory
            )
            issues = cls._issues(
                products, inventory, transit, inventory_date,
                catalog_required=bool(catalog),
            )

            fingerprint_payload = {
                "profile": profile_id,
                "as_of": as_of,
                "inventory_date": inventory_date,
                "sales_through": sales_through,
                "sales_evidence": sales_evidence,
                "products": products,
                "fob_prices": fob_prices,
                "inventory": inventory,
                "transit": transit,
            }
            fingerprint = hashlib.sha256(
                json.dumps(
                    fingerprint_payload, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            snapshot_key = f"SP-{as_of.replace('-', '')}-{uuid4().hex[:12].upper()}"
            cursor = connection.execute(
                """INSERT INTO stock_planning_snapshots (
                    vendor_profile_id, snapshot_key, as_of_date,
                    inventory_snapshot_date, sales_through_date,
                    source_fingerprint, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile_id, snapshot_key, as_of, inventory_date,
                    sales_through, fingerprint, created_by.strip(),
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            cls._freeze_rows(
                connection, snapshot_id, products, inventory, transit, issues,
                fob_prices, sales_evidence,
            )
            if assumptions:
                connection.execute(
                    """INSERT INTO stock_planning_analysis_inputs (
                        snapshot_id,manufacturing_days,
                        international_shipping_days,receiving_days,
                        cali_transfer_days,coverage_months
                    ) VALUES (?,?,?,?,?,?)""",
                    (
                        snapshot_id,
                        _nonnegative_int(assumptions.get("manufacturing_days")),
                        _nonnegative_int(
                            assumptions.get("international_shipping_days")
                        ),
                        _nonnegative_int(assumptions.get("receiving_days")),
                        _nonnegative_int(assumptions.get("cali_transfer_days")),
                        _positive_float(assumptions.get("coverage_months")),
                    ),
                )

        return FrozenPlanningSnapshot(
            snapshot_id=snapshot_id,
            snapshot_key=snapshot_key,
            product_count=len(products),
            inventory_row_count=len(inventory),
            issue_count=len(issues),
            inventory_snapshot_date=inventory_date,
            sales_through_date=sales_through,
        )

    @staticmethod
    def _latest_inventory_date(connection, as_of: str, brands: list[str]) -> str | None:
        if not StockPlanningRepository.table_exists(connection, "inventario_snapshot"):
            return None
        normalized = [_normalize(item) for item in brands if _normalize(item)]
        if not normalized:
            return None
        placeholders = ",".join("?" for _ in normalized)
        row = connection.execute(
            f"""SELECT MAX(fecha_snapshot) AS value FROM inventario_snapshot
            WHERE fecha_snapshot <= ? AND (
                UPPER(TRIM(COALESCE(marca_codigo,''))) IN ({placeholders}) OR
                UPPER(TRIM(COALESCE(marca_nombre,''))) IN ({placeholders})
            )""",
            (as_of, *normalized, *normalized),
        ).fetchone()
        return row["value"] if row else None

    @staticmethod
    def _inventory_rows(
        connection, snapshot_date, brands, branch_codes,
    ) -> list[dict[str, Any]]:
        if not snapshot_date:
            return []
        normalized = [_normalize(item) for item in brands if _normalize(item)]
        placeholders = ",".join("?" for _ in normalized)
        branch_filter = ""
        branch_parameters: list[str] = []
        if branch_codes:
            branch_filter = (
                " AND TRIM(idbodega) IN ("
                + ",".join("?" for _ in branch_codes) + ")"
            )
            branch_parameters = list(branch_codes)
        rows = connection.execute(
            f"""SELECT idbodega, nombre_bodega, idproducto, nombreproducto,
                unidades, unidades_reservado, unidades_remisionado,
                unidades_transito, costo_unitario
            FROM inventario_snapshot
            WHERE fecha_snapshot=? AND (
                UPPER(TRIM(COALESCE(marca_codigo,''))) IN ({placeholders}) OR
                UPPER(TRIM(COALESCE(marca_nombre,''))) IN ({placeholders})
            ){branch_filter} ORDER BY idbodega,idproducto""",
            (snapshot_date, *normalized, *normalized, *branch_parameters),
        ).fetchall()
        result = []
        for row in rows:
            on_hand = float(row["unidades"] or 0)
            reserved = float(row["unidades_reservado"] or 0)
            remitted = float(row["unidades_remisionado"] or 0)
            result.append({
                "branch_code": str(row["idbodega"]).strip(),
                "branch_name": row["nombre_bodega"],
                "internal_sku": _required_sku(row["idproducto"]),
                "product_name": row["nombreproducto"],
                "on_hand": on_hand,
                "reserved": reserved,
                "remitted": remitted,
                "usable": on_hand - reserved - remitted,
                "undated_transit": float(row["unidades_transito"] or 0),
                "dated_transit": 0.0,
                "average_cost": row["costo_unitario"],
            })
        return result

    @staticmethod
    def _sales_products(connection, as_of, suffixes):
        if not StockPlanningRepository.table_exists(connection, "raw_sales"):
            return [], None
        columns = StockPlanningRepository.table_columns(connection, "raw_sales")
        if not {"idproducto", "fecha"}.issubset(columns):
            return [], None
        normalized = [_normalize(item) for item in suffixes if _normalize(item)]
        if "sufijo" not in columns or not normalized:
            return [], None
        placeholders = ",".join("?" for _ in normalized)
        name_sql = "MAX(nombreproducto)" if "nombreproducto" in columns else "NULL"
        rows = connection.execute(
            f"""SELECT UPPER(TRIM(idproducto)) AS internal_sku,
                {name_sql} AS product_name, MAX(fecha) AS last_sale_date
            FROM raw_sales WHERE fecha <= ?
                AND UPPER(TRIM(COALESCE(sufijo,''))) IN ({placeholders})
                AND TRIM(COALESCE(idproducto,'')) <> ''
            GROUP BY UPPER(TRIM(idproducto))""",
            (as_of, *normalized),
        ).fetchall()
        result = [dict(row) for row in rows]
        through = max((row["last_sale_date"] for row in result), default=None)
        return result, through

    @staticmethod
    def _catalog_products(connection, profile_id):
        return [dict(row) for row in connection.execute(
            """SELECT internal_sku,vendor_sku,product_name
            FROM stock_planning_product_catalog
            WHERE vendor_profile_id=? AND is_active=1""", (profile_id,)
        ).fetchall()]

    @staticmethod
    def _transit_rows(connection, profile_id, as_of):
        return [dict(row) for row in connection.execute(
            """SELECT id,branch_code,internal_sku,quantity,expected_date,
                purchase_order_reference FROM stock_planning_transit_supplies
            WHERE vendor_profile_id=? AND transit_status IN ('planned','confirmed','shipped')
                AND (expected_date IS NULL OR expected_date >= ?)
            ORDER BY branch_code,internal_sku,id""", (profile_id, as_of)
        ).fetchall()]

    @staticmethod
    def _relationship_products(connection, profile_id):
        rows = connection.execute(
            """SELECT purchase_sku AS internal_sku
            FROM stock_planning_transformations WHERE vendor_profile_id=?
            UNION SELECT ti.sales_sku FROM stock_planning_transformation_inputs ti
            JOIN stock_planning_transformations t ON t.id=ti.transformation_id
            WHERE t.vendor_profile_id=?
            UNION SELECT fm.internal_sku FROM stock_planning_family_members fm
            JOIN stock_planning_families f ON f.id=fm.family_id
            WHERE f.vendor_profile_id=?""", (profile_id, profile_id, profile_id)
        ).fetchall()
        return [{"internal_sku": row["internal_sku"]} for row in rows]

    @staticmethod
    def _sales_evidence(connection, through, suffixes):
        if not suffixes or not StockPlanningRepository.table_exists(
            connection, "raw_sales"
        ):
            return []
        columns = StockPlanningRepository.table_columns(connection, "raw_sales")
        required = {"fecha", "idproducto", "idbodega", "cantidad", "sufijo"}
        if not required.issubset(columns):
            return []
        raw_name = (
            "NULLIF(TRIM(s.razonsocial),'')" if "razonsocial" in columns else "NULL"
        )
        customer_name = f"COALESCE({raw_name},'Cliente sin nombre')"
        warehouse_name = (
            "COALESCE(NULLIF(TRIM(s.nombrebodega),''),TRIM(s.idbodega))"
            if "nombrebodega" in columns else "TRIM(s.idbodega)"
        )
        net_value = "COALESCE(s.neto,0)" if "neto" in columns else "0"
        marks = ",".join("?" for _ in suffixes)
        rows = connection.execute(
            f"""SELECT date(s.fecha) sale_date,UPPER(TRIM(s.idproducto)) internal_sku,
                TRIM(s.idbodega) branch_code,{warehouse_name} warehouse_name,
                {customer_name} customer_name,
                CAST(COALESCE(s.cantidad,0) AS REAL) quantity,
                CAST({net_value} AS REAL) net_value_cop
            FROM raw_sales s
            WHERE date(s.fecha)<=date(?)
              AND date(s.fecha)>=date(?,'start of month','-35 months')
              AND UPPER(TRIM(s.sufijo)) IN ({marks})
              AND TRIM(s.idbodega) IN ('1','16','50')
            ORDER BY date(s.fecha),s.rowid""",
            (through, through, *[str(value).upper() for value in suffixes]),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _active_branches(connection):
        return [dict(row) for row in connection.execute(
            """SELECT branch_code,branch_name FROM stock_planning_branches
            WHERE is_active=1 ORDER BY branch_code"""
        ).fetchall()]

    @staticmethod
    def _complete_branch_positions(branches, products, inventory):
        if not branches:
            seen = {}
            for row in inventory:
                seen[row["branch_code"]] = row["branch_name"]
            branches = [
                {"branch_code": code, "branch_name": name}
                for code, name in sorted(seen.items())
            ]
        positions = {
            (row["branch_code"], row["internal_sku"]): row
            for row in inventory
        }
        for branch in branches:
            for product in products:
                key = (branch["branch_code"], product["internal_sku"])
                positions.setdefault(key, {
                    "branch_code": branch["branch_code"],
                    "branch_name": branch["branch_name"],
                    "internal_sku": product["internal_sku"],
                    "product_name": product["product_name"],
                    "on_hand": 0.0, "reserved": 0.0, "remitted": 0.0,
                    "usable": 0.0, "undated_transit": 0.0,
                    "dated_transit": 0.0, "average_cost": None,
                })
        return [positions[key] for key in sorted(positions)]

    @staticmethod
    def _build_universe(catalog, inventory, sales, transit, related):
        products: dict[str, dict[str, Any]] = {}
        def add(row, source, **flags):
            sku = _required_sku(row["internal_sku"])
            product = products.setdefault(sku, {
                "internal_sku": sku, "vendor_sku": None,
                "product_name": None, "sources": set(),
                "is_catalog_product": 0, "has_sales_history": 0,
                "has_inventory_history": 0, "has_transit": 0,
            })
            product["sources"].add(source)
            product["vendor_sku"] = product["vendor_sku"] or row.get("vendor_sku")
            product["product_name"] = product["product_name"] or row.get("product_name")
            product.update({key: max(product[key], value) for key, value in flags.items()})
        for row in catalog: add(row, "catalog", is_catalog_product=1)
        for row in inventory: add(row, "inventory", has_inventory_history=1)
        for row in sales: add(row, "sales", has_sales_history=1)
        for row in transit: add(row, "dated_transit", has_transit=1)
        for row in related: add(row, "relationship")
        result = []
        for product in products.values():
            product["sources"] = sorted(product["sources"])
            result.append(product)
        return sorted(result, key=lambda item: item["internal_sku"])

    @staticmethod
    def _issues(
        products, inventory, transit, inventory_date, *, catalog_required=False,
    ):
        issues = []
        if not inventory_date:
            issues.append(("error", "MISSING_INVENTORY_SNAPSHOT", None, None,
                           "No matching inventory snapshot exists.", {}))
        for row in inventory:
            if row["usable"] < 0:
                issues.append(("warning", "NEGATIVE_USABLE_INVENTORY",
                               row["branch_code"], row["internal_sku"],
                               "Reserved and remitted units exceed on-hand stock.", {}))
            if row["undated_transit"] > 0:
                issues.append(("warning", "UNDATED_TRANSIT",
                               row["branch_code"], row["internal_sku"],
                               "ERP transit exists without a dated supply record.",
                               {"quantity": row["undated_transit"]}))
        for row in transit:
            if not row["expected_date"]:
                issues.append(("warning", "UNDATED_TRANSIT",
                               row["branch_code"], row["internal_sku"],
                               "Transit supply has no expected date.",
                               {"quantity": row["quantity"]}))
        for product in products:
            if catalog_required and not product["is_catalog_product"]:
                issues.append(("warning", "PRODUCT_NOT_IN_CATALOG", None,
                               product["internal_sku"],
                               "Product is in operational evidence but not the vendor catalogue.",
                               {"sources": product["sources"]}))
        return issues

    @staticmethod
    def _fob_prices(connection, profile, products):
        aliases = {
            str(value).strip().upper()
            for value in (
                profile.get("inventory_brand_codes", [])
                + profile.get("sales_suffixes", [])
            )
            if str(value).strip()
        }
        product_skus = {product["internal_sku"] for product in products}
        if not aliases or not product_skus:
            return []
        alias_placeholders = ",".join("?" for _ in aliases)
        sku_placeholders = ",".join("?" for _ in product_skus)
        rows = connection.execute(
            f"""SELECT idproducto AS internal_sku,fob_usd,lista1_cop,nit,
                import_execution_id,imported_at,id
            FROM erp_fob_price_history
            WHERE UPPER(sufijo) IN ({alias_placeholders})
              AND idproducto IN ({sku_placeholders})
            ORDER BY imported_at DESC,import_execution_id DESC,id DESC""",
            (*sorted(aliases), *sorted(product_skus)),
        ).fetchall()
        latest = {}
        for row in rows:
            latest.setdefault(row["internal_sku"], dict(row))
        return list(latest.values())

    @staticmethod
    def _freeze_rows(
        connection, snapshot_id, products, inventory, transit, issues,
        fob_prices=None, sales_evidence=None,
    ):
        dated_by_key: dict[tuple[str, str], float] = {}
        for row in transit:
            key = (row["branch_code"], row["internal_sku"])
            dated_by_key[key] = dated_by_key.get(key, 0) + float(row["quantity"])
        connection.executemany(
            """INSERT INTO stock_planning_snapshot_products VALUES (?,?,?,?,?,?,?,?,?)""",
            [(snapshot_id, p["internal_sku"], p["vendor_sku"], p["product_name"],
              json.dumps(p["sources"]), p["is_catalog_product"],
              p["has_sales_history"], p["has_inventory_history"], p["has_transit"])
             for p in products],
        )
        connection.executemany(
            """INSERT INTO stock_planning_snapshot_fob_prices (
                snapshot_id,internal_sku,fob_usd,lista1_cop,supplier_nit,
                price_import_execution_id
            ) VALUES (?,?,?,?,?,?)""",
            [
                (
                    snapshot_id, row["internal_sku"], row["fob_usd"],
                    row["lista1_cop"], row["nit"], row["import_execution_id"],
                )
                for row in (fob_prices or [])
            ],
        )
        connection.executemany(
            """INSERT INTO stock_planning_snapshot_inventory VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [(snapshot_id, r["branch_code"], r["branch_name"], r["internal_sku"],
              r["on_hand"], r["reserved"], r["remitted"], r["usable"],
              r["undated_transit"], dated_by_key.get((r["branch_code"], r["internal_sku"]), 0),
              r["average_cost"]) for r in inventory],
        )
        connection.executemany(
            """INSERT INTO stock_planning_snapshot_transit VALUES (?,?,?,?,?,?,?)""",
            [(snapshot_id, r["id"], r["branch_code"], r["internal_sku"],
              r["quantity"], r["expected_date"], r["purchase_order_reference"])
             for r in transit],
        )
        connection.executemany(
            """INSERT INTO stock_planning_snapshot_sales_movements (
                snapshot_id,sale_date,internal_sku,branch_code,warehouse_name,
                customer_name,quantity,net_value_cop
            ) VALUES (?,?,?,?,?,?,?,?)""",
            [
                (
                    snapshot_id, row["sale_date"], row["internal_sku"],
                    row["branch_code"], row["warehouse_name"],
                    row["customer_name"], row["quantity"], row["net_value_cop"],
                )
                for row in (sales_evidence or [])
            ],
        )
        connection.executemany(
            """INSERT INTO stock_planning_snapshot_issues (
                snapshot_id,severity,issue_code,branch_code,internal_sku,message,details_json
            ) VALUES (?,?,?,?,?,?,?)""",
            [(snapshot_id, severity, code, branch, sku, message, json.dumps(details))
             for severity, code, branch, sku, message, details in issues],
        )


def _normalize(value: Any) -> str:
    return str(value or "").strip().upper()


def _required_text(value: Any) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError("A required value is empty.")
    return result


def _required_code(value: Any) -> str:
    return _required_text(value).upper().replace(" ", "_")


def _required_sku(value: Any) -> str:
    return _required_text(value).upper()


def _nonnegative_int(value: Any) -> int:
    result = int(value)
    if result < 0:
        raise ValueError("Los tiempos no pueden ser negativos.")
    return result


def _positive_float(value: Any) -> float:
    result = float(value)
    if result <= 0:
        raise ValueError("Los meses de cobertura deben ser mayores que cero.")
    return result
