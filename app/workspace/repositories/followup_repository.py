from typing import Any

from app.database.transaction import connection_scope


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

        with connection_scope() as conn:
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

        with connection_scope() as conn:
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

        with connection_scope() as conn:
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

        with connection_scope() as conn:
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

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (followup_id,),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Follow-up does not exist: {followup_id}"
                )

    @staticmethod
    def complete_pending_for_project(project_id: int) -> int:
        """Close every open loop when its opportunity reaches a terminal state."""
        with connection_scope() as conn:
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ws_followups'"
            ).fetchone() is None:
                return 0
            cursor = conn.execute(
                """UPDATE ws_followups
                SET status='completed', completed_at=CURRENT_TIMESTAMP
                WHERE project_id=? AND status='pending'""",
                (project_id,),
            )
        return int(cursor.rowcount)


    @staticmethod
    def list_due_followups() -> list[dict[str, Any]]:
        sql = """
        SELECT
            f.id AS followup_id,
            f.project_id,
            f.due_date,
            f.description,
            f.status,
            p.name AS project_name,
            p.status AS project_status,
            c.id AS customer_id,
            c.name AS customer_name
        FROM ws_followups f
        INNER JOIN ws_projects p
            ON p.id = f.project_id
        INNER JOIN ws_customers c
            ON c.id = p.customer_id
        WHERE
            f.status = 'pending'
            AND p.status NOT IN ('won', 'lost', 'cancelled')
            AND f.due_date <= DATE('now')
        ORDER BY
            f.due_date ASC,
            c.name ASC,
            p.name ASC
        """

        with connection_scope() as conn:
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

        with connection_scope() as conn:
            row = conn.execute(
                sql,
                (followup_id,),
            ).fetchone()

        return dict(row) if row is not None else None

    @staticmethod
    def reschedule_followup(
        followup_id: int,
        due_date: str,
    ) -> None:
        clean_due_date = due_date.strip()

        if not clean_due_date:
            raise ValueError(
                "La nueva fecha de seguimiento es obligatoria."
            )

        sql = """
        UPDATE ws_followups
        SET due_date = ?
        WHERE id = ?
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (
                    clean_due_date,
                    followup_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Follow-up does not exist: {followup_id}"
                )
