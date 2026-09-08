import json
from typing import Any

from app.database.transaction import connection_scope


class RFQVendorRequestRepository:
    @staticmethod
    def pending_rfq_ids() -> list[int]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT DISTINCT rfq_id FROM rfq_vendor_requests
                WHERE status='sent' AND provider_thread_id IS NOT NULL
                ORDER BY rfq_id"""
            ).fetchall()
        return [int(row["rfq_id"]) for row in rows]

    @staticmethod
    def list_for_rfq(rfq_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT vr.*,
                    EXISTS(
                        SELECT 1 FROM rfq_vendor_request_messages m
                        WHERE m.vendor_request_id=vr.id AND m.direction='incoming'
                    ) AS has_response
                FROM rfq_vendor_requests vr
                WHERE vr.rfq_id=? ORDER BY vr.created_at,vr.id""",
                (rfq_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def latest_for_brand(rfq_id: int, brand: str) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT * FROM rfq_vendor_requests
                WHERE rfq_id=? AND brand=? COLLATE NOCASE
                ORDER BY id DESC LIMIT 1""",
                (rfq_id, brand),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def save_message(vendor_request_id: int, message: dict[str, Any]) -> int:
        with connection_scope() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO rfq_vendor_request_messages (
                    vendor_request_id,provider_message_id,direction,sender_email,
                    recipient_emails_json,cc_emails_json,subject,body_text,
                    body_html_sanitized,message_at
                ) VALUES (?,?,?,?,?,?,?,?,?,COALESCE(?,CURRENT_TIMESTAMP))""",
                (
                    vendor_request_id, message["id"], message["direction"],
                    message.get("sender"), json.dumps(message.get("recipients", [])),
                    json.dumps(message.get("cc", [])), message.get("subject"),
                    message.get("body_text"), message.get("body_html"),
                    message.get("date"),
                ),
            )
            row = connection.execute(
                """SELECT id FROM rfq_vendor_request_messages
                WHERE vendor_request_id=? AND provider_message_id=?""",
                (vendor_request_id, message["id"]),
            ).fetchone()
        return int(row["id"])

    @staticmethod
    def save_attachment(message_id: int, values: dict[str, Any]) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO rfq_vendor_response_attachments(
                    vendor_message_id,provider_attachment_id,original_filename,
                    stored_filename,mime_type,size_bytes
                ) VALUES (?,?,?,?,?,?)""",
                (
                    message_id, values.get("provider_attachment_id"),
                    values["original_filename"], values["stored_filename"],
                    values.get("mime_type"), values["size_bytes"],
                ),
            )

    @staticmethod
    def list_attachments(rfq_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT a.*,m.subject,m.direction,vr.brand
                FROM rfq_vendor_response_attachments a
                JOIN rfq_vendor_request_messages m ON m.id=a.vendor_message_id
                JOIN rfq_vendor_requests vr ON vr.id=m.vendor_request_id
                WHERE vr.rfq_id=? ORDER BY a.created_at,a.id""",
                (rfq_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def get_attachment(rfq_id: int, attachment_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT a.* FROM rfq_vendor_response_attachments a
                JOIN rfq_vendor_request_messages m ON m.id=a.vendor_message_id
                JOIN rfq_vendor_requests vr ON vr.id=m.vendor_request_id
                WHERE vr.rfq_id=? AND a.id=?""", (rfq_id, attachment_id),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_messages(rfq_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT m.*,vr.brand,vc.vendor_name
                FROM rfq_vendor_request_messages m
                JOIN rfq_vendor_requests vr ON vr.id=m.vendor_request_id
                JOIN quote_vendor_configs vc ON vc.id=vr.vendor_config_id
                WHERE vr.rfq_id=? ORDER BY m.message_at,m.id""",
                (rfq_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def mark_synced(vendor_request_id: int, has_response: bool) -> None:
        with connection_scope() as connection:
            connection.execute(
                """UPDATE rfq_vendor_requests SET status=?,last_error=NULL
                WHERE id=?""",
                ("responded" if has_response else "sent", vendor_request_id),
            )

    @staticmethod
    def mark_error(vendor_request_id: int, error: str) -> None:
        with connection_scope() as connection:
            connection.execute(
                """UPDATE rfq_vendor_requests SET last_error=? WHERE id=?""",
                (error[:500], vendor_request_id),
            )
