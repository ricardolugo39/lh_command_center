from typing import Any

from app.database.connection import get_connection


class ActivityRepository:

    @staticmethod
    def create_activity(
        project_id: int,
        activity_type: str,
        title: str,
        details: str | None = None,
        created_by: str = "system",
    ) -> int:
        sql = """
        INSERT INTO ws_activities (
            project_id,
            activity_type,
            title,
            details,
            created_by
        )
        VALUES (?, ?, ?, ?, ?)
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    project_id,
                    activity_type,
                    title,
                    details,
                    created_by,
                ),
            )

            conn.commit()

            return int(cursor.lastrowid)

    @staticmethod
    def list_project_activities(
        project_id: int,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            id,
            project_id,
            activity_type,
            title,
            details,
            created_by,
            occurred_at,
            created_at
        FROM ws_activities
        WHERE project_id = ?
        ORDER BY occurred_at DESC, id DESC
        """

        with get_connection() as conn:
            cursor = conn.execute(sql, (project_id,))
            rows = cursor.fetchall()

            columns = [column[0] for column in cursor.description]

            return [
                dict(zip(columns, row))
                for row in rows
            ]