from typing import Any

from app.database.transaction import connection_scope, transactional
from app.workspace.constants.commercial_office import office_for_sales_rep


class ActivityTrainingRepository:
    TRAINING_KEY = "activity_capture"
    TRAINING_VERSION = "2026-10"

    @classmethod
    @transactional
    def start(cls, user_id: int) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO activity_training_completions (
                    user_id,training_key,training_version
                ) VALUES (?,?,?)
                ON CONFLICT(user_id,training_key) DO UPDATE SET
                    training_version=excluded.training_version""",
                (user_id, cls.TRAINING_KEY, cls.TRAINING_VERSION),
            )

    @classmethod
    @transactional
    def complete(cls, user_id: int) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO activity_training_completions (
                    user_id,training_key,training_version,completed_at,attempt_count
                ) VALUES (?,?,?,CURRENT_TIMESTAMP,1)
                ON CONFLICT(user_id,training_key) DO UPDATE SET
                    training_version=excluded.training_version,
                    completed_at=CURRENT_TIMESTAMP,
                    attempt_count=activity_training_completions.attempt_count+1""",
                (user_id, cls.TRAINING_KEY, cls.TRAINING_VERSION),
            )

    @classmethod
    def get(cls, user_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT * FROM activity_training_completions
                WHERE user_id=? AND training_key=?""",
                (user_id, cls.TRAINING_KEY),
            ).fetchone()
        return dict(row) if row else None

    @classmethod
    def report(cls) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT u.id,u.display_name,u.email,u.office,u.role,
                    u.erp_sales_rep_name,
                    c.started_at,c.completed_at,c.attempt_count,c.training_version
                FROM ws_users u
                INNER JOIN user_module_permissions p
                  ON p.user_id=u.id AND p.module_key='activities'
                    AND p.is_enabled=1
                LEFT JOIN activity_training_completions c
                  ON c.user_id=u.id AND c.training_key=?
                WHERE u.is_active=1 AND u.role='advisor'
                ORDER BY c.completed_at IS NULL, u.display_name""",
                (cls.TRAINING_KEY,),
            ).fetchall()
        report = []
        for row in rows:
            item = dict(row)
            item["office"] = office_for_sales_rep(
                item.get("erp_sales_rep_name") or item.get("display_name")
            )
            item["can_login"] = bool(item.get("email"))
            report.append(item)
        return sorted(
            report,
            key=lambda item: (
                item["completed_at"] is None,
                item["office"],
                item["display_name"],
            ),
        )
