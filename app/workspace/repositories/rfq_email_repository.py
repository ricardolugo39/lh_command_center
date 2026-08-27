import json
from typing import Any

from app.database.transaction import connection_scope


class RFQEmailRepository:
    @staticmethod
    def get_thread(rfq_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM rfq_email_threads WHERE rfq_id = ?", (rfq_id,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def save_sent(
        rfq_id: int, *, subject: str, sender: str, recipients: list[str],
        cc: list[str], provider_thread_id: str, provider_message_id: str,
        body_text: str, body_html: str,
    ) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO rfq_email_threads (
                    rfq_id, provider_thread_id, subject, sender_email,
                    recipient_emails_json, cc_emails_json, sent_message_id,
                    sent_at, sync_status, last_synced_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'synced',
                    CURRENT_TIMESTAMP, NULL)
                ON CONFLICT(rfq_id) DO UPDATE SET
                    provider_thread_id=excluded.provider_thread_id,
                    sent_message_id=excluded.sent_message_id,
                    sent_at=excluded.sent_at, sync_status='synced',
                    last_synced_at=CURRENT_TIMESTAMP, last_error=NULL,
                    updated_at=CURRENT_TIMESTAMP""",
                (
                    rfq_id, provider_thread_id, subject, sender,
                    json.dumps(recipients), json.dumps(cc), provider_message_id,
                ),
            )
            thread_id = connection.execute(
                "SELECT id FROM rfq_email_threads WHERE rfq_id = ?", (rfq_id,)
            ).fetchone()[0]
            RFQEmailRepository._insert_message(
                connection, thread_id, {
                    "id": provider_message_id, "direction": "outgoing",
                    "sender": sender, "recipients": recipients, "cc": cc,
                    "subject": subject, "body_text": body_text,
                    "body_html": body_html, "date": None,
                }
            )

    @staticmethod
    def save_messages(rfq_id: int, messages: list[dict[str, Any]]) -> None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT id FROM rfq_email_threads WHERE rfq_id = ?", (rfq_id,)
            ).fetchone()
            if not row:
                return
            for message in messages:
                RFQEmailRepository._insert_message(
                    connection, row[0], message
                )
            connection.execute(
                """UPDATE rfq_email_threads SET sync_status='synced',
                    last_synced_at=CURRENT_TIMESTAMP, last_error=NULL,
                    updated_at=CURRENT_TIMESTAMP WHERE id=?""", (row[0],)
            )

    @staticmethod
    def mark_error(rfq_id: int, error: str) -> None:
        with connection_scope() as connection:
            connection.execute(
                """UPDATE rfq_email_threads SET sync_status='error',
                    last_error=?, updated_at=CURRENT_TIMESTAMP WHERE rfq_id=?""",
                (error[:500], rfq_id),
            )

    @staticmethod
    def list_messages(rfq_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT m.* FROM rfq_email_messages m
                JOIN rfq_email_threads t ON t.id=m.thread_id
                WHERE t.rfq_id=? ORDER BY m.message_at, m.id""", (rfq_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _insert_message(connection, thread_id, message):
        connection.execute(
            """INSERT OR IGNORE INTO rfq_email_messages (
                thread_id, provider_message_id, direction, sender_email,
                recipient_emails_json, cc_emails_json, subject, body_text,
                body_html_sanitized, message_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            (
                thread_id, message["id"], message["direction"],
                message.get("sender"), json.dumps(message.get("recipients", [])),
                json.dumps(message.get("cc", [])), message.get("subject"),
                message.get("body_text"), message.get("body_html"),
                message.get("date"),
            ),
        )
