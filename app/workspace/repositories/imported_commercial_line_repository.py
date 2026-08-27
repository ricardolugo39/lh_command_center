import json
from typing import Any

from app.database.transaction import connection_scope


class ImportedCommercialLineRepository:
    """Imported CRM demand evidence; no user-edit operation is exposed."""

    @staticmethod
    def synchronize(
        opportunity_id: int, *, external_opportunity_id: str,
        origin_reference: str | None, product_lines: list[dict[str, Any]],
        import_execution_id: int,
    ) -> dict[str, int]:
        active_keys: list[str] = []
        inserted = updated = 0
        with connection_scope() as connection:
            for line in product_lines:
                source_key = str(line["source_line_key"])
                active_keys.append(source_key)
                existing = connection.execute(
                    """SELECT id FROM imported_commercial_lines
                    WHERE opportunity_id=? AND source_line_key=?""",
                    (opportunity_id, source_key),
                ).fetchone()
                values = (
                    external_opportunity_id, origin_reference,
                    line.get("brand"), line.get("product_code"),
                    line.get("product_description"),
                    line.get("line_potential_value"),
                    json.dumps(
                        [line["source_row_id"]]
                        if line.get("source_row_id") is not None else []
                    ),
                    json.dumps(
                        [line["source_row_number"]]
                        if line.get("source_row_number") is not None else []
                    ),
                    import_execution_id,
                    json.dumps(line, ensure_ascii=False, default=str),
                )
                if existing:
                    connection.execute(
                        """UPDATE imported_commercial_lines SET
                            origin_opportunity_id=?,origin_reference=?,
                            brand=?,part_number=?,description=?,
                            potential_value=?,crm_row_ids_json=?,
                            crm_row_numbers_json=?,import_execution_id=?,
                            source_metadata_json=?,is_active=1,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=?""",
                        (*values, existing["id"]),
                    )
                    updated += 1
                else:
                    connection.execute(
                        """INSERT INTO imported_commercial_lines(
                            opportunity_id,source_line_key,
                            origin_opportunity_id,origin_reference,brand,
                            part_number,description,potential_value,
                            crm_row_ids_json,crm_row_numbers_json,
                            import_execution_id,source_metadata_json
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (opportunity_id, source_key, *values),
                    )
                    inserted += 1
            if active_keys:
                placeholders = ",".join("?" for _ in active_keys)
                cursor = connection.execute(
                    f"""UPDATE imported_commercial_lines SET
                        is_active=0,updated_at=CURRENT_TIMESTAMP
                    WHERE opportunity_id=? AND is_active=1
                      AND source_line_key NOT IN ({placeholders})""",
                    (opportunity_id, *active_keys),
                )
            else:
                cursor = connection.execute(
                    """UPDATE imported_commercial_lines SET
                        is_active=0,updated_at=CURRENT_TIMESTAMP
                    WHERE opportunity_id=? AND is_active=1""",
                    (opportunity_id,),
                )
        return {
            "inserted": inserted, "updated": updated,
            "deactivated": int(cursor.rowcount),
        }

    @staticmethod
    def list_for_opportunity(
        opportunity_id: int, *, active_only: bool = True
    ) -> list[dict[str, Any]]:
        clause = "AND is_active=1" if active_only else ""
        with connection_scope() as connection:
            rows = connection.execute(
                f"""SELECT * FROM imported_commercial_lines
                WHERE opportunity_id=? {clause}
                ORDER BY id""",
                (opportunity_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["crm_row_ids"] = json.loads(item["crm_row_ids_json"])
            item["crm_row_numbers"] = json.loads(item["crm_row_numbers_json"])
            result.append(item)
        return result

    @staticmethod
    def potential_total(opportunity_id: int) -> float | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT SUM(potential_value)
                FROM imported_commercial_lines
                WHERE opportunity_id=? AND is_active=1""",
                (opportunity_id,),
            ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

