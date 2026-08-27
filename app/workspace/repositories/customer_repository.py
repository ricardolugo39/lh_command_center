from typing import Any

from app.database.transaction import connection_scope


class CustomerRepository:

    @staticmethod
    def create_customer(
        name: str,
        erp_customer_id: str | None = None,
    ) -> int:
        sql = """
        INSERT INTO ws_customers (
            name,
            erp_customer_id
        )
        VALUES (?, ?)
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (
                    name.strip(),
                    erp_customer_id.strip() if erp_customer_id else None,
                ),
            )

            return int(cursor.lastrowid)

    @staticmethod
    def get_customer(customer_id: int) -> dict[str, Any] | None:
        sql = """
        SELECT
            id,
            name,
            erp_customer_id,
            created_at,
            updated_at
        FROM ws_customers
        WHERE id = ?
        """

        with connection_scope() as conn:
            cursor = conn.execute(sql, (customer_id,))
            row = cursor.fetchone()

            if row is None:
                return None

            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, row))

    @staticmethod
    def list_customers() -> list[dict[str, Any]]:
        sql = """
        SELECT
            id,
            name,
            erp_customer_id,
            created_at,
            updated_at
        FROM ws_customers
        ORDER BY name
        """

        with connection_scope() as conn:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]

            return [
                dict(zip(columns, row))
                for row in rows
            ]

    @staticmethod
    def find_by_erp_customer_id(
        erp_customer_id: str,
    ) -> dict[str, Any] | None:
        sql = """
        SELECT
            id,
            name,
            erp_customer_id,
            created_at,
            updated_at
        FROM ws_customers
        WHERE erp_customer_id = ?
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (erp_customer_id.strip(),),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, row))
