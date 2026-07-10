from typing import Any

from app.database.connection import get_connection


VALID_STATUSES = {
    "prospect",
    "quoting",
    "waiting_customer",
    "negotiation",
    "won",
    "lost",
}


class ProjectRepository:

    @staticmethod
    def create_project(
        customer_id: int,
        name: str,
        objective: str,
        status: str = "prospect",
        proposed_solution: str | None = None,
        current_blocker: str | None = None,
    ) -> int:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid project status: {status}")

        if not name.strip():
            raise ValueError("Project name is required")

        if not objective.strip():
            raise ValueError("Project objective is required")

        sql = """
        INSERT INTO ws_projects (
            customer_id,
            name,
            status,
            objective,
            proposed_solution,
            current_blocker
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    customer_id,
                    name.strip(),
                    status,
                    objective.strip(),
                    proposed_solution.strip()
                    if proposed_solution
                    else None,
                    current_blocker.strip()
                    if current_blocker
                    else None,
                ),
            )
            conn.commit()

            return int(cursor.lastrowid)

    @staticmethod
    def get_project(project_id: int) -> dict[str, Any] | None:
        sql = """
        SELECT
            id,
            customer_id,
            name,
            status,
            objective,
            proposed_solution,
            current_blocker,
            created_at,
            updated_at,
            closed_at
        FROM ws_projects
        WHERE id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(sql, (project_id,))
            row = cursor.fetchone()

            if row is None:
                return None

            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, row))

    @staticmethod
    def list_projects(
        customer_id: int | None = None,
    ) -> list[dict[str, Any]]:
        params: tuple[Any, ...] = ()

        sql = """
        SELECT
            id,
            customer_id,
            name,
            status,
            objective,
            proposed_solution,
            current_blocker,
            created_at,
            updated_at,
            closed_at
        FROM ws_projects
        """

        if customer_id is not None:
            sql += "\nWHERE customer_id = ?"
            params = (customer_id,)

        sql += "\nORDER BY updated_at DESC, created_at DESC"

        with get_connection() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]

            return [
                dict(zip(columns, row))
                for row in rows
            ]

    @staticmethod
    def update_project(
        project_id: int,
        *,
        name: str,
        status: str,
        objective: str,
        proposed_solution: str | None,
        current_blocker: str | None,
    ) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid project status: {status}")

        sql = """
        UPDATE ws_projects
        SET
            name = ?,
            status = ?,
            objective = ?,
            proposed_solution = ?,
            current_blocker = ?,
            updated_at = CURRENT_TIMESTAMP,
            closed_at = CASE
                WHEN ? IN ('won', 'lost')
                THEN COALESCE(closed_at, CURRENT_TIMESTAMP)
                ELSE NULL
            END
        WHERE id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    name.strip(),
                    status,
                    objective.strip(),
                    proposed_solution.strip()
                    if proposed_solution
                    else None,
                    current_blocker.strip()
                    if current_blocker
                    else None,
                    status,
                    project_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Project does not exist: {project_id}"
                )

            conn.commit()

    @staticmethod
    def update_status(
        project_id: int,
        new_status: str,
    ) -> None:
        sql = """
        UPDATE ws_projects
        SET
            status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """

        with get_connection() as conn:
            conn.execute(
                sql,
                (
                    new_status,
                    project_id,
                ),
            )
            conn.commit()

    @staticmethod
    def update_blocker(
        project_id: int,
        blocker: str | None,
    ) -> None:

        sql = """
        UPDATE ws_projects
        SET
            current_blocker = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """

        with get_connection() as conn:
            conn.execute(
                sql,
                (
                    blocker,
                    project_id,
                ),
            )
            conn.commit()