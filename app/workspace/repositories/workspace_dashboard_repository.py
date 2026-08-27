from typing import Any

from app.database.connection import get_connection


class WorkspaceDashboardRepository:

    @staticmethod
    def list_pending_followups() -> list[dict[str, Any]]:
        sql = """
        SELECT * FROM (
        SELECT
            f.id AS followup_id,
            'opportunity' AS source_type,
            f.project_id,
            NULL AS visit_id,
            f.description,
            f.due_date,
            f.status,
            f.created_by AS owner_name,
            0 AS reschedule_count,

            p.name AS project_name,
            p.status AS project_status,
            p.sales_rep,

            c.id AS customer_id,
            c.name AS customer_name

        FROM ws_followups AS f

        INNER JOIN ws_projects AS p
            ON p.id = f.project_id

        INNER JOIN ws_customers AS c
            ON c.id = p.customer_id

        WHERE f.status = 'pending'
          AND p.status NOT IN ('won', 'lost', 'cancelled')

        UNION ALL

        SELECT
            vf.id AS followup_id,
            'visit' AS source_type,
            v.project_id,
            v.id AS visit_id,
            COALESCE(vf.description, 'Confirmar compromiso de visita') AS description,
            vf.due_date,
            vf.status,
            vf.owner_name,
            COALESCE(vf.reschedule_count, 0) AS reschedule_count,
            COALESCE(p.name, 'Visita comercial') AS project_name,
            p.status AS project_status,
            COALESCE(vf.owner_name, v.advisor_name) AS sales_rep,
            c.id AS customer_id,
            c.name AS customer_name
        FROM ws_visit_followups AS vf
        INNER JOIN ws_commercial_visits AS v ON v.id = vf.visit_id
        INNER JOIN ws_customers AS c ON c.id = v.customer_id
        LEFT JOIN ws_projects AS p ON p.id = v.project_id
        WHERE vf.status = 'pending' AND v.is_active = 1
        ) AS unified

        ORDER BY
            due_date ASC,
            followup_id ASC
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
