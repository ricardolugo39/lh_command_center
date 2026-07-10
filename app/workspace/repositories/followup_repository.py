from typing import Any

from app.database.connection import get_connection


class FollowupRepository:

    @staticmethod
    def find_pending_duplicate(
        *,
        project_id: int,
        due_date: str,
        description: str,
    ) -> dict[str, Any] | None:
        sql = """
        SELECT *
        FROM ws_followups
        WHERE
            project_id = ?
            AND due_date = ?
            AND description = ?
            AND status = 'pending'
        LIMIT 1
        """

        with get_connection() as conn:
            row = conn.execute(
                sql,
                (
                    project_id,
                    due_date,
                    description,
                ),
            ).fetchone()

        return dict(row) if row is not None else None

    @staticmethod
    def create_followup(
        *,
        project_id: int,
        due_date: str,
        description: str,
        status: str,
        created_by: str = "system",
    ) -> int:
        sql = """
        INSERT INTO ws_followups (
            project_id,
            due_date,
            description,
            status,
            created_by
        )
        VALUES (?, ?, ?, ?, ?)
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    project_id,
                    due_date,
                    description,
                    status,
                    created_by,
                ),
            )
            conn.commit()

            return int(cursor.lastrowid)

    @staticmethod
    def get_followup(
        followup_id: int,
    ) -> dict[str, Any] | None:
        sql = """
        SELECT *
        FROM ws_followups
        WHERE id = ?
        """

        with get_connection() as conn:
            row = conn.execute(
                sql,
                (followup_id,),
            ).fetchone()

        return dict(row) if row is not None else None

    @staticmethod
    def list_project_followups(
        project_id: int,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT *
        FROM ws_followups
        WHERE project_id = ?
        ORDER BY due_date ASC, id ASC
        """

        with get_connection() as conn:
            rows = conn.execute(
                sql,
                (project_id,),
            ).fetchall()

        return [dict(row) for row in rows]

    @staticmethod
    def complete_followup(
        followup_id: int,
    ) -> None:
        sql = """
        UPDATE ws_followups
        SET
            status = 'completed',
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (followup_id,),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Follow-up does not exist: {followup_id}"
                )

            conn.commit()

    @staticmethod
    def list_due_followups() -> list[dict[str, Any]]:
        sql = """
        SELECT *
        FROM ws_followups
        WHERE
            status = 'pending'
            AND due_date <= DATE('now')
        ORDER BY due_date ASC, id ASC
        """

        with get_connection() as conn:
            rows = conn.execute(sql).fetchall()

        return [dict(row) for row in rows]

    @staticmethod
    def get_followup(
        followup_id: int,
    ) -> dict[str, Any] | None:

        sql = """
        SELECT *
        FROM ws_followups
        WHERE id = ?
        """

        with get_connection() as conn:
            row = conn.execute(
                sql,
                (followup_id,),
            ).fetchone()

        return dict(row) if row is not None else None