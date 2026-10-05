from typing import Any

from app.database.transaction import connection_scope, transactional


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
                    c.started_at,c.completed_at,c.attempt_count,c.training_version
                FROM ws_users u
                LEFT JOIN activity_training_completions c
                  ON c.user_id=u.id AND c.training_key=?
                WHERE u.is_active=1 AND u.role IN ('advisor','commercial_management')
                ORDER BY c.completed_at IS NULL, u.office, u.display_name""",
                (cls.TRAINING_KEY,),
            ).fetchall()
        return [dict(row) for row in rows]
