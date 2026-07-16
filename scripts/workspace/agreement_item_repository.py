from typing import Any

from app.database.connection import get_connection



class AgreementItemRepository:

    @staticmethod
    def replace_agreement_items(
        *,
        agreement_id: int,
        items: list[dict[str, Any]],
    ) -> int:

        with get_connection() as conn:

            conn.execute(
                """
                DELETE FROM ws_agreement_items
                WHERE agreement_id = ?
                """,
                (agreement_id,),
            )

            sql = """
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
            """

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
                sql,
                rows,
            )

            conn.commit()

        return len(rows)

    @staticmethod
    def list_agreement_items(
        agreement_id: int,
    ) -> list[dict]:

        with get_connection() as conn:

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
                c[0]
                for c in cursor.description
            ]

            return [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]