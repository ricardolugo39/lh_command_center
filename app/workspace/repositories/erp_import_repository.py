import json
from datetime import datetime, timezone
from sqlite3 import Connection
from typing import Any, Iterable

from app.database.transaction import connection_scope
from app.workspace.customer_identity import (
    customer_site_key, normalize_nit, normalize_site_text,
)


class ERPImportRepository:
    """Persistence for auditable ERP imports; business decisions live in services."""

    @staticmethod
    def create_execution(values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """
                INSERT INTO erp_import_executions (
                    import_type, original_filename, stored_file_path,
                    file_hash, schema_version, status, rows_read,
                    warnings_json, errors_json, execution_log_json,
                    executed_by, customers_inserted, customers_updated,
                    customers_unchanged, customer_sites_inserted,
                    customer_sites_updated, customer_sites_unchanged,
                    snapshot_date, mapping_profile_version_id,
                    groups_identified, groups_to_create, groups_to_update,
                    groups_unchanged, groups_needs_review, groups_blocked,
                    customer_resolutions_json, groups_eligible,
                    groups_imported, groups_deferred
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["import_type"],
                    values["original_filename"],
                    values["stored_file_path"],
                    values["file_hash"],
                    values["schema_version"],
                    values["status"],
                    values.get("rows_read", 0),
                    json.dumps(values.get("warnings", []), ensure_ascii=False),
                    json.dumps(values.get("errors", []), ensure_ascii=False),
                    json.dumps(values.get("log", {}), ensure_ascii=False),
                    values["executed_by"],
                    values.get("customers_inserted", 0),
                    values.get("customers_updated", 0),
                    values.get("customers_unchanged", 0),
                    values.get("customer_sites_inserted", 0),
                    values.get("customer_sites_updated", 0),
                    values.get("customer_sites_unchanged", 0),
                    values.get("snapshot_date"),
                    values.get("mapping_profile_version_id"),
                    values.get("groups_identified", 0),
                    values.get("groups_to_create", 0),
                    values.get("groups_to_update", 0),
                    values.get("groups_unchanged", 0),
                    values.get("groups_needs_review", 0),
                    values.get("groups_blocked", 0),
                    json.dumps(
                        values.get("customer_resolutions", {}),
                        ensure_ascii=False,
                    ),
                    values.get("groups_eligible", 0),
                    values.get("groups_imported", 0),
                    values.get("groups_deferred", 0),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def update_execution(execution_id: int, values: dict[str, Any]) -> None:
        assignments = []
        parameters: list[Any] = []
        json_fields = {
            "warnings": "warnings_json",
            "errors": "errors_json",
            "log": "execution_log_json",
            "customer_resolutions": "customer_resolutions_json",
        }
        allowed = {
            "status", "rows_read", "rows_inserted", "rows_updated",
            "rows_skipped", "duplicates_count", "completed_at",
            "customers_inserted", "customers_updated", "customers_unchanged",
            "customer_sites_inserted", "customer_sites_updated",
            "customer_sites_unchanged",
            "mapping_profile_version_id", "groups_identified",
            "groups_to_create", "groups_to_update", "groups_unchanged",
            "groups_needs_review", "groups_blocked",
            "groups_eligible", "groups_imported", "groups_deferred",
        }
        for key, value in values.items():
            if key in json_fields:
                assignments.append(f"{json_fields[key]} = ?")
                parameters.append(json.dumps(value, ensure_ascii=False))
            elif key in allowed:
                assignments.append(f"{key} = ?")
                parameters.append(value)
        if not assignments:
            return
        parameters.append(execution_id)
        with connection_scope() as connection:
            connection.execute(
                f"UPDATE erp_import_executions SET {', '.join(assignments)} "
                "WHERE id = ?",
                tuple(parameters),
            )

    @staticmethod
    def get_execution(execution_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM erp_import_executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_executions(limit: int = 50) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT * FROM erp_import_executions
                ORDER BY started_at DESC, id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def existing_sales_keys(keys: Iterable[str]) -> set[str]:
        values = tuple(keys)
        if not values:
            return set()
        found: set[str] = set()
        with connection_scope() as connection:
            for start in range(0, len(values), 500):
                batch = values[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    f"SELECT sales_line_key FROM raw_sales "
                    f"WHERE sales_line_key IN ({placeholders})",
                    batch,
                ).fetchall()
                found.update(row[0] for row in rows)
        return found

    @staticmethod
    def existing_inventory_keys(
        keys: Iterable[tuple[str, str, str]],
    ) -> set[tuple[str, str, str]]:
        values = tuple(keys)
        if not values:
            return set()
        found: set[tuple[str, str, str]] = set()
        with connection_scope() as connection:
            for start in range(0, len(values), 150):
                batch = values[start:start + 150]
                clauses = " OR ".join(
                    "(fecha_snapshot=? AND idbodega=? AND idproducto=?)"
                    for _ in batch
                )
                parameters = tuple(value for key in batch for value in key)
                rows = connection.execute(
                    """SELECT fecha_snapshot, idbodega, idproducto
                    FROM inventario_snapshot WHERE """ + clauses,
                    parameters,
                ).fetchall()
                found.update((row[0], row[1], row[2]) for row in rows)
        return found

    @staticmethod
    def known_inventory_warehouses() -> set[str]:
        with connection_scope() as connection:
            rows = connection.execute(
                "SELECT DISTINCT idbodega FROM inventario_snapshot"
            ).fetchall()
        return {str(row[0]) for row in rows}

    @staticmethod
    def upsert_inventory(rows: list[dict[str, Any]]) -> tuple[int, int]:
        if not rows:
            return 0, 0
        keys = {
            (
                str(row["fecha_snapshot"]),
                str(row["idbodega"]),
                str(row["idproducto"]),
            )
            for row in rows
        }
        existing = ERPImportRepository.existing_inventory_keys(keys)
        columns = [
            "fecha_snapshot", "idbodega", "nombre_bodega", "idproducto",
            "nombreproducto", "unidad_medida", "unidades",
            "idfam1", "nombre_fam1", "idfam2", "nombre_fam2",
            "idfam3", "nombre_fam3", "marca_codigo", "marca_nombre",
            "grupo_fabricante_codigo", "grupo_fabricante_nombre",
            "unidades_disponible", "unidades_reservado",
            "unidades_remisionado", "transito_1", "transito_2",
            "transito_3", "unidades_transito", "costo_unitario",
            "valor_total", "ultima_entrada", "ubicacion", "codigo_barras",
            "archivo_origen",
        ]
        updates = [
            column for column in columns
            if column not in {"fecha_snapshot", "idbodega", "idproducto"}
        ]
        sql = (
            f"INSERT INTO inventario_snapshot ({','.join(columns)}) VALUES "
            f"({','.join('?' for _ in columns)}) "
            "ON CONFLICT(fecha_snapshot,idbodega,idproducto) DO UPDATE SET "
            + ",".join(
                f"{column}=excluded.{column}" for column in updates
            )
            + ",fecha_carga=CURRENT_TIMESTAMP"
        )
        with connection_scope() as connection:
            connection.executemany(
                sql,
                [tuple(row.get(column) for column in columns) for row in rows],
            )
        return len(keys - existing), len(keys & existing)

    @staticmethod
    def insert_fob_prices(
        execution_id: int, rows: list[dict[str, Any]]
    ) -> int:
        if not rows:
            return 0
        columns = (
            "idproducto", "prefijo", "sufijo", "idfam2", "fob_usd",
            "lista1_cop", "nit",
        )
        with connection_scope() as connection:
            connection.executemany(
                """INSERT INTO erp_fob_price_history (
                    import_execution_id,idproducto,prefijo,sufijo,idfam2,
                    fob_usd,lista1_cop,nit
                ) VALUES (?,?,?,?,?,?,?,?)""",
                [
                    (execution_id, *(row.get(column) for column in columns))
                    for row in rows
                ],
            )
        return len(rows)

    @staticmethod
    def create_issues(
        execution_id: int, issues: Iterable[Any]
    ) -> None:
        values = list(issues)
        if not values:
            return
        with connection_scope() as connection:
            connection.executemany(
                """INSERT INTO erp_import_issues (
                    import_execution_id, row_number, severity, code,
                    message, details_json
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        execution_id,
                        issue.row_number,
                        issue.severity,
                        issue.code,
                        issue.message,
                        json.dumps(issue.details, ensure_ascii=False),
                    )
                    for issue in values
                ],
            )

    @staticmethod
    def list_issues(execution_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT row_number, severity, code, message, details_json
                FROM erp_import_issues
                WHERE import_execution_id=?
                ORDER BY CASE severity WHEN 'error' THEN 0 ELSE 1 END,
                    row_number, id""",
                (execution_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def insert_sales(rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        with connection_scope() as connection:
            columns = ERPImportRepository._table_columns(connection, "raw_sales")
            usable = [column for column in columns if column in rows[0]]
            sql = (
                f"INSERT INTO raw_sales ({','.join(usable)}) VALUES "
                f"({','.join('?' for _ in usable)})"
            )
            connection.executemany(
                sql,
                [tuple(row.get(column) for column in usable) for row in rows],
            )
        return len(rows)

    @staticmethod
    def plan_customer_sync(
        customers: list[dict[str, Any]], sites: list[dict[str, Any]]
    ) -> dict[str, Any]:
        with connection_scope() as connection:
            existing_customers = {
                normalize_nit(row["erp_customer_id"]):
                dict(row)
                for row in connection.execute(
                    """SELECT id, name, erp_customer_id FROM ws_customers
                    WHERE erp_customer_id IS NOT NULL"""
                ).fetchall()
            }
            raw_columns = ERPImportRepository._table_columns(
                connection, "raw_customers"
            )
            existing_sites = {}
            for row in connection.execute("SELECT * FROM raw_customers"):
                value = dict(row)
                key = customer_site_key(value)
                # Keep the first physical row for legacy exact duplicates.
                existing_sites.setdefault(key, value)

        customer_actions = []
        for customer in customers:
            current = existing_customers.get(customer["nit"])
            if not current:
                action = "insert"
            elif str(current["name"]).strip() != customer["name"]:
                action = "update"
                customer["id"] = current["id"]
            else:
                action = "unchanged"
                customer["id"] = current["id"]
            customer_actions.append((action, customer))

        site_actions = []
        usable_columns = [
            column for column in raw_columns
            if column.casefold() in sites[0] and column.casefold() != "id"
        ] if sites else []
        update_columns = [
            column for column in usable_columns
            if column.casefold() not in {"nit", "ciudad", "direccion1"}
        ]
        for site in sites:
            current = existing_sites.get(site["_sync_site_key"])
            if not current:
                action = "insert"
            elif ERPImportRepository._site_changed(
                current, site, update_columns
            ):
                action = "update"
            else:
                action = "unchanged"
            site_actions.append((action, site))

        metrics = {
            "customers_inserted": sum(a == "insert" for a, _ in customer_actions),
            "customers_updated": sum(a == "update" for a, _ in customer_actions),
            "customers_unchanged": sum(
                a == "unchanged" for a, _ in customer_actions
            ),
            "customer_sites_inserted": sum(
                a == "insert" for a, _ in site_actions
            ),
            "customer_sites_updated": sum(
                a == "update" for a, _ in site_actions
            ),
            "customer_sites_unchanged": sum(
                a == "unchanged" for a, _ in site_actions
            ),
        }
        return {
            "customer_actions": customer_actions,
            "site_actions": site_actions,
            "site_columns": usable_columns,
            "site_update_columns": update_columns,
            "metrics": metrics,
        }

    @staticmethod
    def apply_customer_sync(plan: dict[str, Any]) -> None:
        with connection_scope() as connection:
            for action, customer in plan["customer_actions"]:
                if action == "insert":
                    connection.execute(
                        """INSERT INTO ws_customers(name, erp_customer_id)
                        VALUES (?, ?)""", (customer["name"], customer["nit"])
                    )
                elif action == "update":
                    connection.execute(
                        """UPDATE ws_customers SET name=?,
                            updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (customer["name"], customer["id"]),
                    )

            columns = plan["site_columns"]
            update_columns = plan["site_update_columns"]
            for action, site in plan["site_actions"]:
                if action == "insert":
                    connection.execute(
                        f'INSERT INTO raw_customers '
                        f'({",".join(ERPImportRepository._quote(c) for c in columns)}) '
                        f'VALUES ({",".join("?" for _ in columns)})',
                        tuple(site.get(column.casefold()) for column in columns),
                    )
                elif action == "update":
                    assignments = ", ".join(
                        f"{ERPImportRepository._quote(column)}=?"
                        for column in update_columns
                    )
                    where, parameters = ERPImportRepository._site_where(site)
                    connection.execute(
                        f"UPDATE raw_customers SET {assignments} "
                        f"WHERE {where}",
                        tuple(
                            site.get(column.casefold())
                            for column in update_columns
                        )
                        + parameters,
                    )

    @staticmethod
    def _site_changed(
        current: dict[str, Any], incoming: dict[str, Any],
        columns: list[str],
    ) -> bool:
        return any(
            ERPImportRepository._comparable(current.get(column))
            != ERPImportRepository._comparable(incoming.get(column.casefold()))
            for column in columns
        )

    @staticmethod
    def _site_where(site: dict[str, Any]) -> tuple[str, tuple[str, str, str]]:
        normalized_nit = (
            "UPPER(REPLACE(REPLACE(REPLACE(REPLACE(TRIM(COALESCE(nit,'')),"
            "' ',''),'.',''),'-',''),',',''))"
        )
        return (
            f"{normalized_nit}=? AND UPPER(TRIM(COALESCE(ciudad,'')))=? "
            "AND UPPER(TRIM(COALESCE(direccion1,'')))=?",
            (
                normalize_nit(site.get("nit")),
                normalize_site_text(site.get("ciudad")),
                normalize_site_text(site.get("direccion1")),
            ),
        )

    @staticmethod
    def _comparable(value: Any) -> str:
        return "" if value is None else str(value).strip()

    @staticmethod
    def _quote(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def upsert_customers(rows: list[dict[str, Any]]) -> tuple[int, int]:
        """Backward-compatible adapter for callers using the old repository API."""
        if not rows:
            return 0, 0
        sites = []
        customers = {}
        for row in rows:
            nit = normalize_nit(row.get("nit"))
            normalized = {str(k).casefold(): v for k, v in row.items()}
            normalized["nit"] = nit
            normalized["_sync_site_key"] = customer_site_key(normalized)
            sites.append(normalized)
            customers.setdefault(nit, {
                "nit": nit, "name": str(row.get("razonsocial") or "").strip(),
            })
        plan = ERPImportRepository.plan_customer_sync(
            list(customers.values()), sites
        )
        ERPImportRepository.apply_customer_sync(plan)
        metrics = plan["metrics"]
        return metrics["customer_sites_inserted"], metrics["customer_sites_updated"]

    @staticmethod
    def completed_at() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _table_columns(connection: Connection, table_name: str) -> list[str]:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        if not rows:
            raise RuntimeError(f"No existe la tabla ERP requerida: {table_name}.")
        return [row["name"] for row in rows]
