from typing import Any

from app.database.transaction import connection_scope


class UserRepository:
    @staticmethod
    def first_active() -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT * FROM ws_users WHERE is_active=1
                ORDER BY role='administrator' DESC, role='system', id"""
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get(user_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM ws_users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_by_email(email: str) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT * FROM ws_users
                WHERE email_normalized = ? OR LOWER(TRIM(email)) = ?""",
                (email.strip().casefold(), email.strip().casefold()),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_by_google_subject(subject: str) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM ws_users WHERE google_subject = ?", (subject,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def link_google_identity(
        user_id: int, *, subject: str, email: str, display_name: str
    ) -> None:
        with connection_scope() as connection:
            connection.execute(
                """UPDATE ws_users SET google_subject = ?, email = ?,
                    email_normalized = ?, display_name = ?,
                    last_login_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
                (
                    subject, email.strip(), email.strip().casefold(),
                    display_name.strip(), user_id,
                ),
            )
