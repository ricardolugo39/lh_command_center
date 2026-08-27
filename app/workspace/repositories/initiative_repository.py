from typing import Any

from app.database.transaction import connection_scope


VALID_INITIATIVE_STATUSES = {
    "planning",
    "active",
    "paused",
    "completed",
}


class InitiativeRepository:

    @staticmethod
    def create_initiative(
        *,
        name: str,
        status: str,
        objective: str,
        owner: str,
        description: str | None = None,
        strategy: str | None = None,
        partner: str | None = None,
        start_date: str | None = None,
        expected_end_date: str | None = None,
    ) -> int:
        sql = """
        INSERT INTO ws_initiatives (
            name,
            status,
            objective,
            description,
            strategy,
            partner,
            owner,
            start_date,
            expected_end_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (
                    name.strip(),
                    status,
                    objective.strip(),
                    description.strip()
                    if description
                    else None,
                    strategy.strip()
                    if strategy
                    else None,
                    partner.strip()
                    if partner
                    else None,
                    owner.strip(),
                    start_date or None,
                    expected_end_date or None,
                ),
            )


            return int(cursor.lastrowid)

    @staticmethod
    def get_initiative(
        initiative_id: int,
    ) -> dict[str, Any] | None:
        sql = """
        SELECT
            id,
            name,
            status,
            objective,
            description,
            strategy,
            partner,
            owner,
            start_date,
            expected_end_date,
            created_at,
            updated_at,
            closed_at
        FROM ws_initiatives
        WHERE id = ?
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (initiative_id,),
            )

            row = cursor.fetchone()

            if row is None:
                return None

            columns = [
                column[0]
                for column in cursor.description
            ]

            return dict(zip(columns, row))

    @staticmethod
    def list_initiatives() -> list[dict[str, Any]]:
        sql = """
        SELECT
            i.id,
            i.name,
            i.status,
            i.objective,
            i.partner,
            i.owner,
            i.start_date,
            i.expected_end_date,
            i.created_at,
            i.updated_at,

            COUNT(
                DISTINCT p.id
            ) AS opportunity_count,

            COALESCE(
                SUM(
                    CASE
                        WHEN p.status NOT IN (
                            'won',
                            'lost'
                        )
                        THEN q.normalized_amount
                        ELSE 0
                    END
                ),
                0
            ) AS pipeline_cop

        FROM ws_initiatives AS i

        LEFT JOIN ws_projects AS p
            ON p.initiative_id = i.id

        LEFT JOIN ws_project_quotes AS q
            ON q.id = (
                SELECT q2.id
                FROM ws_project_quotes AS q2
                WHERE q2.project_id = p.id
                ORDER BY q2.id DESC
                LIMIT 1
            )

        GROUP BY
            i.id,
            i.name,
            i.status,
            i.objective,
            i.partner,
            i.owner,
            i.start_date,
            i.expected_end_date,
            i.created_at,
            i.updated_at

        ORDER BY
            CASE i.status
                WHEN 'active' THEN 1
                WHEN 'planning' THEN 2
                WHEN 'paused' THEN 3
                WHEN 'completed' THEN 4
                ELSE 5
            END,
            i.updated_at DESC
        """

        with connection_scope() as conn:
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
    def create_event(
        *,
        initiative_id: int,
        event_type: str,
        title: str,
        details: str | None = None,
        created_by: str = "system",
    ) -> int:
        sql = """
        INSERT INTO ws_initiative_events (
            initiative_id,
            event_type,
            title,
            details,
            created_by
        )
        VALUES (?, ?, ?, ?, ?)
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (
                    initiative_id,
                    event_type.strip(),
                    title.strip(),
                    details.strip()
                    if details
                    else None,
                    created_by.strip(),
                ),
            )


            return int(cursor.lastrowid)

    @staticmethod
    def list_events(
        initiative_id: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            id,
            initiative_id,
            event_type,
            title,
            details,
            occurred_at,
            created_at,
            created_by
        FROM ws_initiative_events
        WHERE initiative_id = ?
        ORDER BY
            occurred_at DESC,
            id DESC
        LIMIT ?
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (
                    initiative_id,
                    limit,
                ),
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

    @staticmethod
    def list_related_opportunities(
        initiative_id: int,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            p.id,
            p.name,
            p.status,
            p.current_blocker,
            p.sales_rep,
            p.updated_at,

            c.name AS customer_name,

            q.amount,
            q.currency_code,
            q.normalized_amount,
            q.prefix,
            q.quote_number

        FROM ws_projects AS p

        INNER JOIN ws_customers AS c
            ON c.id = p.customer_id

        LEFT JOIN ws_project_quotes AS q
            ON q.id = (
                SELECT q2.id
                FROM ws_project_quotes AS q2
                WHERE q2.project_id = p.id
                ORDER BY q2.id DESC
                LIMIT 1
            )

        WHERE p.initiative_id = ?

        ORDER BY
            p.updated_at DESC
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (initiative_id,),
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

    @staticmethod
    def delete_initiative(
        initiative_id: int,
    ) -> None:
        with connection_scope() as conn:
            conn.execute("PRAGMA foreign_keys = ON")

            initiative = conn.execute(
                """
                SELECT id
                FROM ws_initiatives
                WHERE id = ?
                """,
                (initiative_id,),
            ).fetchone()

            if initiative is None:
                raise ValueError(
                    f"Initiative does not exist: {initiative_id}"
                )

            conn.execute(
                """
                UPDATE ws_projects
                SET
                    initiative_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE initiative_id = ?
                """,
                (initiative_id,),
            )

            # Se eliminan explícitamente para que el proceso
            # también funcione si foreign_keys no estaba activo
            # en alguna conexión anterior.
            conn.execute(
                """
                DELETE FROM ws_initiative_events
                WHERE initiative_id = ?
                """,
                (initiative_id,),
            )

            conn.execute(
                """
                DELETE FROM ws_initiative_learnings
                WHERE initiative_id = ?
                """,
                (initiative_id,),
            )

            conn.execute(
                """
                DELETE FROM ws_initiative_decisions
                WHERE initiative_id = ?
                """,
                (initiative_id,),
            )

            conn.execute(
                """
                DELETE FROM ws_initiatives
                WHERE id = ?
                """,
                (initiative_id,),
            )


    @staticmethod
    def update_initiative(
        *,
        initiative_id: int,
        name: str,
        status: str,
        objective: str,
        owner: str,
        description: str | None = None,
        strategy: str | None = None,
        partner: str | None = None,
        start_date: str | None = None,
        expected_end_date: str | None = None,
    ) -> None:
        sql = """
        UPDATE ws_initiatives
        SET
            name = ?,
            status = ?,
            objective = ?,
            description = ?,
            strategy = ?,
            partner = ?,
            owner = ?,
            start_date = ?,
            expected_end_date = ?,
            updated_at = CURRENT_TIMESTAMP,
            closed_at = CASE
                WHEN ? = 'completed'
                THEN COALESCE(
                    closed_at,
                    CURRENT_TIMESTAMP
                )
                ELSE NULL
            END
        WHERE id = ?
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (
                    name.strip(),
                    status,
                    objective.strip(),
                    description.strip()
                    if description
                    else None,
                    strategy.strip()
                    if strategy
                    else None,
                    partner.strip()
                    if partner
                    else None,
                    owner.strip(),
                    start_date or None,
                    expected_end_date or None,
                    status,
                    initiative_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    "La iniciativa no existe."
                )
