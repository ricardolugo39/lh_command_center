from typing import Any

from app.database.connection import get_connection


class ProjectFileRepository:

    @staticmethod
    def create_file(
        *,
        project_id: int,
        category: str,
        original_name: str,
        stored_name: str,
        mime_type: str | None,
        file_size: int | None,
        uploaded_by: str | None,
    ) -> int:
        sql = """
        INSERT INTO ws_project_files (
            project_id,
            category,
            original_name,
            stored_name,
            mime_type,
            file_size,
            uploaded_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    project_id,
                    category,
                    original_name,
                    stored_name,
                    mime_type,
                    file_size,
                    uploaded_by,
                ),
            )
            conn.commit()

            return int(cursor.lastrowid)

    @staticmethod
    def get_file(
        file_id: int,
    ) -> dict[str, Any] | None:
        sql = """
        SELECT
            id,
            project_id,
            category,
            original_name,
            stored_name,
            mime_type,
            file_size,
            uploaded_by,
            created_at
        FROM ws_project_files
        WHERE id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (file_id,),
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
    def list_project_files(
        project_id: int,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            id,
            project_id,
            category,
            original_name,
            stored_name,
            mime_type,
            file_size,
            uploaded_by,
            created_at
        FROM ws_project_files
        WHERE project_id = ?
        ORDER BY
            created_at DESC,
            id DESC
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (project_id,),
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
    def delete_file(
        file_id: int,
    ) -> None:
        sql = """
        DELETE FROM ws_project_files
        WHERE id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (file_id,),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    "El archivo no existe."
                )

            conn.commit()