from typing import Any

from app.database.transaction import connection_scope
from app.workspace.constants.opportunity_origin import OpportunityOrigin
from app.workspace.constants.commercial_office import sql_office_case


class ProjectRepository:

    FILTER_COLUMNS = {
        "status": "p.status",
        "sales_rep": "p.sales_rep",
        "origin": "p.origin",
    }

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
        origin: str = OpportunityOrigin.MANUAL,
        external_id: str | None = None,
        origin_reference: str | None = None,
        imported_at: str | None = None,
        created_import_execution_id: int | None = None,
        last_import_execution_id: int | None = None,
        import_metadata: str | None = None,
    ) -> int:
        clean_name = name.strip()
        clean_objective = objective.strip()

        if not clean_name:
            raise ValueError("Project name is required")

        if not clean_objective:
            raise ValueError("Project objective is required")
        clean_origin = OpportunityOrigin.normalize(origin)
        clean_external_id = (
            str(external_id).strip() if external_id is not None else None
        ) or None
        if clean_origin == OpportunityOrigin.CRM and not clean_external_id:
            raise ValueError("CRM Opportunities require an external ID")
        clean_origin_reference = (
            str(origin_reference).strip()
            if origin_reference is not None
            else None
        ) or None

        sql = """
        INSERT INTO ws_projects (
            customer_id,
            customer_site_id,
            sales_rep,
            name,
            status,
            objective,
            proposed_solution,
            current_blocker,
            origin,
            external_id,
            origin_reference,
            imported_at,
            last_synchronized_at,
            created_import_execution_id,
            last_import_execution_id,
            import_metadata
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        with connection_scope() as conn:
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
                    clean_origin,
                    clean_external_id,
                    clean_origin_reference,
                    imported_at,
                    imported_at,
                    created_import_execution_id,
                    last_import_execution_id,
                    import_metadata,
                ),
            )

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
            commercial_amount,
            commercial_currency,
            origin,
            external_id,
            origin_reference,
            imported_at,
            last_synchronized_at,
            created_import_execution_id,
            last_import_execution_id,
            import_metadata,
            created_at,
            updated_at,
            closed_at
        FROM ws_projects
        WHERE id = ?
        """

        with connection_scope() as conn:
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
            commercial_amount,
            commercial_currency,
            origin,
            external_id,
            origin_reference,
            imported_at,
            last_synchronized_at,
            created_import_execution_id,
            last_import_execution_id,
            import_metadata,
            created_at,
            updated_at,
            closed_at
        FROM ws_projects
        """

        if customer_id is not None:
            sql += "\nWHERE customer_id = ?"
            params = (customer_id,)

        sql += "\nORDER BY updated_at DESC, created_at DESC"

        with connection_scope() as conn:
            rows = conn.execute(
                sql,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    @staticmethod
    def list_project_overviews(
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return list-page data in one query.

        ``filters`` contains normalized persistence criteria. Adding a
        direct equality filter only requires registering its column in
        ``FILTER_COLUMNS``; specialized filters can append their own
        parameterized clause below.
        """
        filters = filters or {}
        clauses: list[str] = []
        params: list[Any] = []

        for key, column in ProjectRepository.FILTER_COLUMNS.items():
            value = filters.get(key)
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)

        customer_name = filters.get("customer_name")
        if customer_name:
            clauses.append("LOWER(c.name) LIKE ?")
            params.append(f"%{customer_name.lower()}%")

        if not filters.get("include_closed"):
            clauses.append("p.status NOT IN ('won', 'lost', 'cancelled')")

        office = filters.get("office")
        if office in {"Bogotá", "Cali"}:
            clauses.append(f"{sql_office_case('p.sales_rep')} = ?")
            params.append(office)

        where_sql = (
            "WHERE " + " AND ".join(clauses)
            if clauses
            else ""
        )

        sql = f"""
        WITH ranked_quotes AS (
            SELECT
                q.*,
                ROW_NUMBER() OVER (
                    PARTITION BY q.project_id
                    ORDER BY q.revision ASC, q.id ASC
                ) AS project_rank
            FROM ws_project_quotes AS q
        ),
        overdue_followups AS (
            SELECT project_id, 1 AS has_overdue_followup
            FROM ws_followups
            WHERE
                status = 'pending'
                AND due_date < DATE('now')
            GROUP BY project_id
        ),
        last_activities AS (
            SELECT project_id, MAX(occurred_at) AS last_activity_at
            FROM ws_activities
            GROUP BY project_id
        ),
        next_followups AS (
            SELECT project_id, MIN(due_date) AS next_action_date
            FROM ws_followups
            WHERE status = 'pending'
            GROUP BY project_id
        ),
        crm_potential AS (
            SELECT opportunity_id, SUM(potential_value) AS potential_value
            FROM imported_commercial_lines
            WHERE is_active = 1
            GROUP BY opportunity_id
        )
        SELECT
            p.id,
            p.customer_id,
            p.customer_site_id,
            p.initiative_id,
            p.sales_rep,
            p.name,
            p.status,
            p.objective,
            p.proposed_solution,
            p.current_blocker,
            p.commercial_amount,
            p.commercial_currency,
            p.origin,
            p.external_id,
            p.origin_reference,
            p.imported_at,
            p.last_synchronized_at,
            p.created_import_execution_id,
            p.last_import_execution_id,
            p.import_metadata,
            p.created_at,
            p.updated_at,
            p.closed_at,
            json_extract(
                p.import_metadata, '$.source_facts.source_updated_at'
            ) AS crm_source_date,
            json_extract(
                p.import_metadata, '$.source_facts.close_date'
            ) AS crm_close_date,
            json_extract(
                p.import_metadata, '$.source_facts.crm_status'
            ) AS crm_status,
            json_extract(
                p.import_metadata, '$.source_facts.crm_stage'
            ) AS crm_stage,
            c.name AS customer_name,
            q.id AS quote_id,
            q.prefix AS quote_prefix,
            q.quote_number,
            q.quote_date,
            q.amount AS quote_amount,
            q.currency_code AS quote_currency_code,
            q.exchange_rate AS quote_exchange_rate,
            q.exchange_rate_type AS quote_exchange_rate_type,
            q.normalized_amount AS quote_normalized_amount,
            q.quote_status,
            q.revision AS quote_revision,
            cp.potential_value AS crm_potential_value,
            COALESCE(of.has_overdue_followup, 0)
                AS has_overdue_followup,
            la.last_activity_at,
            nf.next_action_date
        FROM ws_projects AS p
        INNER JOIN ws_customers AS c
            ON c.id = p.customer_id
        LEFT JOIN ranked_quotes AS q
            ON q.project_id = p.id
            AND q.project_rank = 1
        LEFT JOIN overdue_followups AS of
            ON of.project_id = p.id
        LEFT JOIN last_activities AS la
            ON la.project_id = p.id
        LEFT JOIN next_followups AS nf
            ON nf.project_id = p.id
        LEFT JOIN crm_potential AS cp
            ON cp.opportunity_id = p.id
        {where_sql}
        ORDER BY p.updated_at DESC, p.created_at DESC
        """

        with connection_scope() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [dict(row) for row in rows]

    @staticmethod
    def find_by_origin_external_id(
        origin: str, external_id: str
    ) -> dict[str, Any] | None:
        clean_origin = OpportunityOrigin.normalize(origin)
        clean_external_id = str(external_id or "").strip()
        if not clean_external_id:
            return None
        with connection_scope() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM ws_projects
                WHERE origin = ? AND external_id = ?
                """,
                (clean_origin, clean_external_id),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_by_origin(origin: str) -> dict[str, dict[str, Any]]:
        clean_origin = OpportunityOrigin.normalize(origin)
        with connection_scope() as conn:
            rows = conn.execute(
                """SELECT * FROM ws_projects
                WHERE origin=? AND external_id IS NOT NULL
                  AND TRIM(external_id)<>''""",
                (clean_origin,),
            ).fetchall()
        return {str(row["external_id"]): dict(row) for row in rows}

    @staticmethod
    def update_synchronization_audit(
        project_id: int,
        *,
        last_synchronized_at: str,
        last_import_execution_id: int,
        import_metadata: str | None,
    ) -> None:
        with connection_scope() as conn:
            cursor = conn.execute(
                """
                UPDATE ws_projects
                SET
                    last_synchronized_at = ?,
                    last_import_execution_id = ?,
                    import_metadata = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    last_synchronized_at,
                    last_import_execution_id,
                    import_metadata,
                    project_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Project does not exist: {project_id}")

    @staticmethod
    def synchronize_imported_fields(
        project_id: int,
        values: dict[str, Any],
        *,
        last_synchronized_at: str,
        last_import_execution_id: int,
        import_metadata: str,
    ) -> None:
        """Update only explicitly import-owned parent fields.

        Commercial value, lifecycle closure data, and child records are
        deliberately outside this operation.
        """
        allowed = {"name", "objective", "sales_rep", "status"}
        assignments: list[str] = []
        parameters: list[Any] = []
        for field in sorted(allowed & values.keys()):
            assignments.append(f"{field} = ?")
            parameters.append(values[field])
        assignments.extend([
            "last_synchronized_at = ?",
            "last_import_execution_id = ?",
            "import_metadata = ?",
            "updated_at = CURRENT_TIMESTAMP",
        ])
        parameters.extend([
            last_synchronized_at, last_import_execution_id,
            import_metadata, project_id,
        ])
        with connection_scope() as conn:
            cursor = conn.execute(
                f"UPDATE ws_projects SET {', '.join(assignments)} WHERE id = ?",
                tuple(parameters),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Project does not exist: {project_id}")

    @staticmethod
    def update_commercial_amount(
        project_id: int, *, amount: str, currency: str
    ) -> None:
        with connection_scope() as conn:
            cursor = conn.execute("""
                UPDATE ws_projects
                SET commercial_amount=?, commercial_currency=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (amount, currency, project_id))
            if cursor.rowcount == 0:
                raise ValueError(f"Project does not exist: {project_id}")

    @staticmethod
    def get_commercial_amount(project_id: int) -> dict[str, Any] | None:
        with connection_scope() as conn:
            row = conn.execute("""
                SELECT commercial_amount, commercial_currency
                FROM ws_projects WHERE id=?
            """, (project_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_sales_representatives() -> list[str]:
        sql = """
        SELECT DISTINCT TRIM(sales_rep) AS sales_rep
        FROM ws_projects
        WHERE TRIM(COALESCE(sales_rep, '')) <> ''
        ORDER BY sales_rep COLLATE NOCASE ASC
        """

        with connection_scope() as conn:
            rows = conn.execute(sql).fetchall()

        return [row["sales_rep"] for row in rows]

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

        with connection_scope() as conn:
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

        with connection_scope() as conn:
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

        with connection_scope() as conn:
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

        with connection_scope() as conn:
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

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (project_id,),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Project does not exist: {project_id}"
                )


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

        with connection_scope() as conn:
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

        with connection_scope() as conn:
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

        with connection_scope() as conn:
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

    @staticmethod
    def reopen_project(project_id: int) -> None:
        with connection_scope() as conn:
            cursor = conn.execute(
                """UPDATE ws_projects SET status='negotiation', closed_at=NULL,
                updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (project_id,),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Project does not exist: {project_id}")

    @staticmethod
    def delete_project(
        project_id: int,
    ) -> None:
        with connection_scope() as conn:
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
