from typing import Any

from app.database.transaction import connection_scope


class AgreementAnalyticsRepository:
    """Read-only persistence for agreement performance analytics."""

    @staticmethod
    def get_customer(customer_id: int) -> dict[str, Any] | None:
        with connection_scope() as conn:
            row = conn.execute(
                "SELECT id, erp_customer_id FROM ws_customers WHERE id = ?",
                (customer_id,),
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_items(agreement_id: int) -> list[dict[str, Any]]:
        with connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT id, internal_sku, manufacturer_part_number,
                    normalized_reference, part_number, description, product_line,
                    negotiated_price_decimal, negotiated_price, price_currency,
                    source_row_number
                FROM ws_agreement_items
                WHERE agreement_id = ?
                ORDER BY COALESCE(source_row_number, id)
                """,
                (agreement_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def get_previous_agreement(
        customer_id: int, agreement_id: int, start_date: str
    ) -> dict[str, Any] | None:
        with connection_scope() as conn:
            row = conn.execute(
                """
                SELECT * FROM ws_agreements
                WHERE customer_id = ? AND id <> ?
                  AND start_date IS NOT NULL AND start_date < ?
                ORDER BY start_date DESC, id DESC LIMIT 1
                """,
                (customer_id, agreement_id, start_date),
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_sales(
        erp_customer_id: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        with connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT date(s.fecha) AS sale_date, s.idproducto AS product_key,
                    s.nombreproducto AS product_name, s.idfam1 AS family_id,
                    COALESCE(fd.family_name, 'Sin clasificar') AS family_name,
                    SUM(COALESCE(s.neto, 0)) AS revenue
                FROM raw_sales s
                LEFT JOIN (
                    SELECT family_id, MAX(family_name) AS family_name
                    FROM dim_product_category GROUP BY family_id
                ) fd ON CAST(fd.family_id AS REAL) = s.idfam1
                WHERE REPLACE(s.nit, ',', '') = ?
                  AND date(s.fecha) BETWEEN date(?) AND date(?)
                GROUP BY sale_date, s.idproducto, s.nombreproducto,
                    s.idfam1, fd.family_name
                """,
                (erp_customer_id, start_date, end_date),
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def list_known_product_keys(erp_customer_id: str) -> list[str]:
        with connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT idproducto FROM raw_sales
                WHERE REPLACE(nit, ',', '') = ? AND idproducto IS NOT NULL
                """,
                (erp_customer_id,),
            ).fetchall()
            return [row[0] for row in rows]
