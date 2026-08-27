from typing import Any

from app.database.transaction import connection_scope


class QuoteLineRepository:
    @staticmethod
    def create(
        quote_id: int, *, brand: str | None, part_number: str | None,
        description: str, quantity: float, unit_price: float,
        currency_code: str = "COP",
        imported_commercial_line_id: int | None = None,
        display_order: int = 0,
    ) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO ws_quote_lines(
                    quote_id,imported_commercial_line_id,brand,part_number,
                    description,quantity,unit_price,line_total,
                    currency_code,display_order
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    quote_id, imported_commercial_line_id,
                    brand, part_number, description, quantity, unit_price,
                    quantity * unit_price, currency_code, display_order,
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def list_for_quote(quote_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT l.*,i.source_line_key,i.origin_opportunity_id
                FROM ws_quote_lines l
                LEFT JOIN imported_commercial_lines i
                  ON i.id=l.imported_commercial_line_id
                WHERE l.quote_id=?
                ORDER BY l.display_order,l.id""",
                (quote_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def get(line_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM ws_quote_lines WHERE id=?", (line_id,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def update(
        line_id: int, *, brand: str | None, part_number: str | None,
        description: str, quantity: float, unit_price: float,
    ) -> None:
        with connection_scope() as connection:
            cursor = connection.execute(
                """UPDATE ws_quote_lines SET
                    brand=?,part_number=?,description=?,quantity=?,
                    unit_price=?,line_total=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (
                    brand, part_number, description, quantity, unit_price,
                    quantity * unit_price, line_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("Quote line not found.")

    @staticmethod
    def delete(line_id: int) -> None:
        with connection_scope() as connection:
            connection.execute(
                "DELETE FROM ws_quote_lines WHERE id=?", (line_id,)
            )

    @staticmethod
    def total(quote_id: int) -> float:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(line_total),0) FROM ws_quote_lines "
                "WHERE quote_id=?",
                (quote_id,),
            ).fetchone()
        return float(row[0])
