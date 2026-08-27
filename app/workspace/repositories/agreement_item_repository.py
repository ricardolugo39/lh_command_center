from typing import Any

from app.database.transaction import connection_scope


class AgreementItemRepository:

    @staticmethod
    def insert_imported_items(
        agreement_id: int,
        items: list[dict[str, Any]],
        source_file_name: str,
    ) -> int:
        rows = [(
            agreement_id,
            item.get("internal_sku") or item.get("manufacturer_part_number") or "",
            (item.get("manufacturer_part_number") or item.get("internal_sku") or "")
            + f"@{item.get('source_row_number')}",
            source_file_name,
            item.get("source_row_number"),
            item.get("internal_sku"),
            item.get("manufacturer_part_number"),
            item.get("description"),
            None,
            item.get("currency"),
            item.get("unit_of_measure"),
            item.get("product_start_date"),
            item.get("product_end_date"),
            item.get("notes"),
            item.get("normalized_reference"),
            str(item["list_price"]) if item.get("list_price") is not None else None,
            str(item["negotiated_price"]) if item.get("negotiated_price") is not None else None,
            str(item["suggested_price"]) if item.get("suggested_price") is not None else None,
            item.get("product_line"),
            item.get("spc"),
        ) for item in items]
        with connection_scope() as conn:
            conn.executemany("""
                INSERT INTO ws_agreement_items (
                    agreement_id, part_number, skf_reference, source_file_name,
                    source_row_number, internal_sku, manufacturer_part_number,
                    description, negotiated_price, price_currency,
                    unit_of_measure, product_start_date, product_end_date,
                    item_notes, normalized_reference, list_price_decimal,
                    negotiated_price_decimal, suggested_price_decimal,
                    product_line, spc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
        return len(rows)

    @staticmethod
    def list_imported_items(
        agreement_id: int, *, search: str = "", limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        pattern = f"%{search.strip()}%"
        with connection_scope() as conn:
            cursor = conn.execute("""
                SELECT * FROM ws_agreement_items
                WHERE agreement_id = ? AND (
                    ? = '%%' OR COALESCE(internal_sku, part_number) LIKE ?
                    OR COALESCE(manufacturer_part_number, skf_reference) LIKE ?
                    OR COALESCE(description, '') LIKE ?
                )
                ORDER BY COALESCE(source_row_number, id) LIMIT ? OFFSET ?
            """, (agreement_id, pattern, pattern, pattern, pattern, limit, offset))
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @staticmethod
    def replace_agreement_items(
        *,
        agreement_id: int,
        items: list[dict[str, Any]],
    ) -> int:
        with connection_scope() as conn:
            conn.execute(
                """
                DELETE FROM ws_agreement_items
                WHERE agreement_id = ?
                """,
                (agreement_id,),
            )

            rows = [
                (
                    agreement_id,
                    item["part_number"],
                    item["skf_reference"],
                    item["list_price_usd"],
                    item["agreement_price_usd"],
                    item["suggested_price_usd"],
                    item["product_line"],
                    item["spc"],
                    item.get("source_file_name"),
                )
                for item in items
            ]

            conn.executemany(
                """
                INSERT INTO ws_agreement_items (
                    agreement_id,
                    part_number,
                    skf_reference,
                    list_price_usd,
                    agreement_price_usd,
                    suggested_price_usd,
                    product_line,
                    spc,
                    source_file_name
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

        return len(rows)

    @staticmethod
    def list_agreement_items(
        agreement_id: int,
    ) -> list[dict[str, Any]]:
        with connection_scope() as conn:
            cursor = conn.execute(
                """
                SELECT *
                FROM ws_agreement_items
                WHERE agreement_id = ?
                ORDER BY skf_reference
                """,
                (agreement_id,),
            )

            columns = [
                column[0]
                for column in cursor.description
            ]

            return [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

    @staticmethod
    def count_items(
        agreement_id: int,
    ) -> int:

        with connection_scope() as conn:

            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM ws_agreement_items
                WHERE agreement_id = ?
                """,
                (agreement_id,),
            )

            return cursor.fetchone()[0]
