from app.database.connection import get_connection
from app.database.transaction import connection_scope


class CustomerLookupRepository:

    @staticmethod
    def search_workspace_customers(
        text: str, limit: int = 10,
    ) -> list[dict]:
        clean_text = text.strip()
        if not clean_text:
            return []
        search = f"%{clean_text}%"
        with connection_scope() as conn:
            rows = conn.execute(
                """SELECT id AS workspace_customer_id,
                    name AS customer_name, erp_customer_id AS nit,
                    erp_customer_id AS erp_id
                FROM ws_customers
                WHERE name LIKE ? COLLATE NOCASE
                   OR erp_customer_id LIKE ? COLLATE NOCASE
                ORDER BY
                    CASE
                        WHEN name LIKE ? COLLATE NOCASE THEN 0
                        WHEN name LIKE ? COLLATE NOCASE THEN 1
                        ELSE 2
                    END,
                    INSTR(LOWER(name), LOWER(?)),
                    name, id
                LIMIT ?""",
                (
                    search, search, f"{clean_text}%", f"% {clean_text}%",
                    clean_text,
                    min(max(limit, 1), 20),
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def search(
        text: str,
        limit: int = 20,
    ) -> list[dict]:
        clean_text = text.strip()

        if not clean_text:
            return []

        search_text = f"%{clean_text}%"

        sql = """
        SELECT DISTINCT
            customer_site_id,
            customer_id,
            customer_name,
            city,
            address,
            seller
        FROM dim_customer
        WHERE
            customer_name LIKE ?
            OR customer_id LIKE ?
            OR city LIKE ?
        ORDER BY
            customer_name,
            city,
            address
        LIMIT ?
        """

        with get_connection() as conn:
            rows = conn.execute(
                sql,
                (
                    search_text,
                    search_text,
                    search_text,
                    limit,
                ),
            ).fetchall()

        return [dict(row) for row in rows]

    @staticmethod
    def get_customer_site(
        customer_site_id: str,
    ) -> dict | None:
        sql = """
        SELECT
            customer_site_id,
            customer_id,
            customer_name,
            address,
            city,
            seller,
            has_credit,
            credit_limit,
            payment_terms,
            activity_id_source,
            activity_name,
            classification_name,
            commercial_group_name
        FROM dim_customer
        WHERE customer_site_id = ?
        LIMIT 1
        """

        with get_connection() as conn:
            row = conn.execute(
                sql,
                (customer_site_id,),
            ).fetchone()

        return dict(row) if row is not None else None

    @staticmethod
    def list_customer_sites(
        customer_id: str,
    ) -> list[dict]:
        sql = """
        SELECT DISTINCT
            customer_site_id,
            customer_id,
            customer_name,
            address,
            city,
            seller
        FROM dim_customer
        WHERE customer_id = ?
        ORDER BY
            city,
            address
        """

        with get_connection() as conn:
            rows = conn.execute(
                sql,
                (customer_id,),
            ).fetchall()

        return [dict(row) for row in rows]
