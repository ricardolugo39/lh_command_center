from typing import Any
from sqlite3 import OperationalError

from app.database.transaction import connection_scope


class ActivityRepository:

    @staticmethod
    def create_activity(
        project_id: int | None,
        activity_type: str,
        title: str,
        details: str | None = None,
        created_by: str = "system",
        occurred_at: str | None = None,
        *,
        customer_id: int | None = None,
        contact_id: int | None = None,
        advisor_user_id: int | None = None,
        purpose: str | None = None,
        summary: str | None = None,
        identified_need: str | None = None,
        identified_risk: str | None = None,
        supplier_participated: bool = False,
        supplier_name: str | None = None,
        supplier_person_name: str | None = None,
        supplier_person_role: str | None = None,
        supplier_objective: str | None = None,
        agreement_id: int | None = None,
        potential_value: float | None = None,
        currency_code: str | None = None,
        city: str | None = None,
        site_name: str | None = None,
        visited_area: str | None = None,
    ) -> int:
        sql = """
        INSERT INTO ws_activities (
            customer_id,
            project_id,
            contact_id,
            advisor_user_id,
            activity_type,
            title,
            details,
            purpose,
            summary,
            identified_need,
            identified_risk,
            supplier_participated,
            supplier_name,
            supplier_person_name,
            supplier_person_role,
            supplier_objective,
            agreement_id,
            potential_value,
            currency_code,
            city,
            site_name,
            visited_area,
            created_by,
            occurred_at
        )
        VALUES (
            COALESCE(?, (SELECT customer_id FROM ws_projects WHERE id = ?)),
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, COALESCE(?, CURRENT_TIMESTAMP)
        )
        """

        parameters = (
                    customer_id,
                    project_id,
                    project_id,
                    contact_id,
                    advisor_user_id,
                    activity_type,
                    title,
                    details,
                    purpose,
                    summary or details,
                    identified_need,
                    identified_risk,
                    int(supplier_participated),
                    supplier_name,
                    supplier_person_name,
                    supplier_person_role,
                    supplier_objective,
                    agreement_id,
                    potential_value,
                    currency_code,
                    city,
                    site_name,
                    visited_area,
                    created_by,
                    occurred_at,
                )
        with connection_scope() as conn:
            try:
                cursor = conn.execute(sql, parameters)
            except OperationalError as error:
                if "no column named customer_id" not in str(error):
                    raise
                if project_id is None:
                    raise RuntimeError(
                        "La base de datos requiere la migración de actividades."
                    ) from error
                cursor = conn.execute(
                    """INSERT INTO ws_activities (
                        project_id, activity_type, title, details,
                        created_by, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
                    (
                        project_id, activity_type, title, details,
                        created_by, occurred_at,
                    ),
                )
            return int(cursor.lastrowid)

    @staticmethod
    def add_participants(activity_id: int, user_ids: list[int]) -> None:
        if not user_ids:
            return
        with connection_scope() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO activity_participants
                (activity_id, user_id) VALUES (?, ?)""",
                [(activity_id, user_id) for user_id in user_ids],
            )

    @staticmethod
    def add_results(activity_id: int, results: list[str]) -> None:
        if not results:
            return
        with connection_scope() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO activity_results
                (activity_id, result_type) VALUES (?, ?)""",
                [(activity_id, result) for result in results],
            )

    @staticmethod
    def add_evidence(activity_id: int, values: dict[str, Any]) -> int:
        with connection_scope() as conn:
            cursor = conn.execute(
                """INSERT INTO activity_evidence (
                    activity_id, original_filename, stored_filename,
                    mime_type, size_bytes, description,
                    uploaded_by_user_id, display_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    activity_id, values["original_filename"],
                    values["stored_filename"], values["mime_type"],
                    values["size_bytes"], values.get("description"),
                    values.get("uploaded_by_user_id"),
                    values.get("display_order", 0),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def add_history(
        activity_id: int, event_type: str, snapshot_json: str,
        changed_by_user_id: int | None,
    ) -> None:
        with connection_scope() as conn:
            conn.execute(
                """INSERT INTO activity_history (
                    activity_id, event_type, snapshot_json, changed_by_user_id
                ) VALUES (?, ?, ?, ?)""",
                (activity_id, event_type, snapshot_json, changed_by_user_id),
            )

    @staticmethod
    def list_customer_activities(
        customer_id: int, limit: int = 100
    ) -> list[dict[str, Any]]:
        with connection_scope() as conn:
            rows = conn.execute(
                """SELECT a.*, c.full_name AS contact_name,
                    p.name AS project_name, u.display_name AS advisor_name
                FROM ws_activities a
                LEFT JOIN contacts c ON c.id = a.contact_id
                LEFT JOIN ws_projects p ON p.id = a.project_id
                LEFT JOIN ws_users u ON u.id = a.advisor_user_id
                WHERE a.customer_id = ?
                ORDER BY a.occurred_at DESC, a.id DESC LIMIT ?""",
                (customer_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

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

        with connection_scope() as conn:
            cursor = conn.execute(sql, (project_id,))
            rows = cursor.fetchall()

            columns = [column[0] for column in cursor.description]

            return [
                dict(zip(columns, row))
                for row in rows
            ]
