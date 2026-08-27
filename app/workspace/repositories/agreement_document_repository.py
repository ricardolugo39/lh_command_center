from typing import Any

from app.database.transaction import connection_scope


class AgreementDocumentRepository:
    @staticmethod
    def create(agreement_id: int, original_name: str, stored_name: str,
               mime_type: str | None, file_size: int,
               file_extension: str) -> int:
        with connection_scope() as connection:
            cursor = connection.execute("""
                INSERT INTO ws_agreement_documents (
                    agreement_id, original_name, stored_name, mime_type, file_size,
                    file_extension
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (agreement_id, original_name, stored_name, mime_type, file_size,
                    file_extension))
            return int(cursor.lastrowid)

    @staticmethod
    def get_for_agreement(agreement_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            cursor = connection.execute("""
                SELECT * FROM ws_agreement_documents
                WHERE agreement_id = ? ORDER BY id DESC LIMIT 1
            """, (agreement_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
