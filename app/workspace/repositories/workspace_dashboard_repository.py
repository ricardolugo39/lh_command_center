from typing import Any

from app.database.connection import get_connection


class WorkspaceDashboardRepository:

    @staticmethod
    def list_pending_followups() -> list[dict[str, Any]]:
        sql = """
        SELECT
            f.id AS followup_id,
            f.project_id,
            f.description,
            f.due_date,
            f.status,

            p.name AS project_name,
            p.status AS project_status,

            c.id AS customer_id,
            c.name AS customer_name

        FROM ws_followups AS f

        INNER JOIN ws_projects AS p
            ON p.id = f.project_id

        INNER JOIN ws_customers AS c
            ON c.id = p.customer_id

        WHERE f.status = 'pending'

        ORDER BY
            f.due_date ASC,
            f.id ASC
        """

        with get_connection() as conn:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            columns = [
                column[0]
                for column in cursor.description
            ]

        return [
            dict(zip(columns, row))
            for row in rows
        ]

    @staticmethod
    def list_recent_projects(
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            p.id,
            p.name,
            p.status,
            p.current_blocker,
            p.updated_at,

            c.name AS customer_name

        FROM ws_projects AS p

        INNER JOIN ws_customers AS c
            ON c.id = p.customer_id

        ORDER BY
            p.updated_at DESC,
            p.created_at DESC

        LIMIT ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (limit,),
            )

            rows = cursor.fetchall()
            columns = [
                column[0]
                for column in cursor.description
            ]

        return [
            dict(zip(columns, row))
            for row in rows
        ]