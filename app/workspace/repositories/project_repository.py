from typing import Any

from app.database.connection import get_connection


class ProjectRepository:

    @staticmethod
    def create_project(
        customer_id: int,
        name: str,
        objective: str,
        status: str = "prospect",
        proposed_solution: str | None = None,
        current_blocker: str | None = None,
        customer_site_id: str | None = None,
        sales_rep: str | None = None,
    ) -> int:
        clean_name = name.strip()
        clean_objective = objective.strip()

        if not clean_name:
            raise ValueError("Project name is required")

        if not clean_objective:
            raise ValueError("Project objective is required")

        sql = """
        INSERT INTO ws_projects (
            customer_id,
            customer_site_id,
            sales_rep,
            name,
            status,
            objective,
            proposed_solution,
            current_blocker
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    customer_id,
                    customer_site_id,
                    sales_rep.strip() if sales_rep else None,
                    clean_name,
                    status,
                    clean_objective,
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
    def get_project(
        project_id: int,
    ) -> dict[str, Any] | None:
        sql = """
        SELECT
            id,
            customer_id,
            customer_site_id,
            initiative_id,
            sales_rep,
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
            row = conn.execute(
                sql,
                (project_id,),
            ).fetchone()

        return dict(row) if row is not None else None

    @staticmethod
    def list_projects(
        customer_id: int | None = None,
    ) -> list[dict[str, Any]]:
        params: tuple[Any, ...] = ()

        sql = """
        SELECT
            id,
            customer_id,
            customer_site_id,
            sales_rep,
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
            rows = conn.execute(
                sql,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    @staticmethod
    def update_project(
        project_id: int,
        *,
        name: str,
        objective: str,
        proposed_solution: str | None,
        current_blocker: str | None,
        sales_rep: str | None = None,
    ) -> None:
        clean_name = name.strip()
        clean_objective = objective.strip()

        if not clean_name:
            raise ValueError(
                "El nombre del proyecto es obligatorio."
            )

        if not clean_objective:
            raise ValueError(
                "El objetivo del proyecto es obligatorio."
            )

        sql = """
        UPDATE ws_projects
        SET
            name = ?,
            objective = ?,
            proposed_solution = ?,
            current_blocker = ?,
            sales_rep = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    clean_name,
                    clean_objective,
                    proposed_solution.strip()
                    if proposed_solution
                    else None,
                    current_blocker.strip()
                    if current_blocker
                    else None,
                    sales_rep.strip()
                    if sales_rep
                    else None,
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
            cursor = conn.execute(
                sql,
                (
                    new_status,
                    project_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Project does not exist: {project_id}"
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
            cursor = conn.execute(
                sql,
                (
                    blocker.strip() if blocker else None,
                    project_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Project does not exist: {project_id}"
                )

            conn.commit()

    @staticmethod
    def list_unassigned_projects() -> list[dict[str, Any]]:
        sql = """
        SELECT
            p.id,
            p.customer_id,
            p.name,
            p.status,
            p.objective,
            p.current_blocker,
            p.created_at,
            p.updated_at,

            c.name AS customer_name

        FROM ws_projects AS p

        INNER JOIN ws_customers AS c
            ON c.id = p.customer_id

        WHERE p.initiative_id IS NULL

        ORDER BY
            c.name ASC,
            p.updated_at DESC
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
    def assign_to_initiative(
        *,
        project_id: int,
        initiative_id: int,
    ) -> None:
        sql = """
        UPDATE ws_projects
        SET
            initiative_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    initiative_id,
                    project_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Project does not exist: {project_id}"
                )

            conn.commit()

    @staticmethod
    def remove_from_initiative(
        *,
        project_id: int,
    ) -> None:
        sql = """
        UPDATE ws_projects
        SET
            initiative_id = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (project_id,),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Project does not exist: {project_id}"
                )

            conn.commit()

    @staticmethod
    def close_as_won(
        *,
        project_id: int,
        won_amount: float,
        customer_po: str | None,
        order_number: str | None,
        comments: str | None,
    ) -> None:
        sql = """
        UPDATE ws_projects
        SET
            status = 'won',
            closed_at = CURRENT_TIMESTAMP,
            won_amount = ?,
            customer_po = ?,
            order_number = ?,
            close_comments = ?,
            close_reason = NULL,
            result_changer = NULL,
            competitor_company = NULL,
            competitor_type = NULL,
            competitor_brand = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    won_amount,
                    customer_po.strip() if customer_po else None,
                    order_number.strip() if order_number else None,
                    comments.strip() if comments else None,
                    project_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Project does not exist: {project_id}"
                )

            conn.commit()

    @staticmethod
    def close_as_lost(
        *,
        project_id: int,
        lost_reason: str,
        result_changer: str | None,
        competitor_company: str | None,
        competitor_type: str | None,
        competitor_brand: str | None,
        comments: str | None,
    ) -> None:
        sql = """
        UPDATE ws_projects
        SET
            status = 'lost',
            closed_at = CURRENT_TIMESTAMP,
            close_reason = ?,
            result_changer = ?,
            competitor_company = ?,
            competitor_type = ?,
            competitor_brand = ?,
            close_comments = ?,
            won_amount = NULL,
            customer_po = NULL,
            order_number = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    lost_reason.strip(),
                    result_changer.strip()
                    if result_changer
                    else None,
                    competitor_company.strip()
                    if competitor_company
                    else None,
                    competitor_type.strip()
                    if competitor_type
                    else None,
                    competitor_brand.strip()
                    if competitor_brand
                    else None,
                    comments.strip() if comments else None,
                    project_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Project does not exist: {project_id}"
                )

            conn.commit()

    @staticmethod
    def cancel_project(
        *,
        project_id: int,
        reason: str,
        comments: str | None,
    ) -> None:
        sql = """
        UPDATE ws_projects
        SET
            status = 'cancelled',
            closed_at = CURRENT_TIMESTAMP,
            close_reason = ?,
            close_comments = ?,
            result_changer = NULL,
            won_amount = NULL,
            customer_po = NULL,
            order_number = NULL,
            competitor_company = NULL,
            competitor_type = NULL,
            competitor_brand = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    reason.strip(),
                    comments.strip() if comments else None,
                    project_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Project does not exist: {project_id}"
                )

            conn.commit()
    @staticmethod
    def delete_project(
        project_id: int,
    ) -> None:
        with get_connection() as conn:
            conn.execute("PRAGMA foreign_keys = ON")

            cursor = conn.execute(
                """
                DELETE FROM ws_projects
                WHERE id = ?
                """,
                (project_id,),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Project does not exist: {project_id}"
                )

            conn.commit()
