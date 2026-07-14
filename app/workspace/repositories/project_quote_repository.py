from typing import Any

from app.database.connection import get_connection


class ProjectQuoteRepository:

    @staticmethod
    def attach_quote(
        *,
        project_id: int,
        quote_number: str,
        prefix: str = "CTC",
        branch: str | None = None,
        quote_date: str | None = None,
        amount: float | None = None,
        quote_status: str | None = None,
        erp_user: str | None = None,
    ) -> int:
        clean_number = quote_number.strip().replace(",", "")
        clean_prefix = prefix.strip().upper()

        if not clean_number:
            raise ValueError("Quote number is required")

        if not clean_prefix:
            raise ValueError("Quote prefix is required")

        sql = """
        INSERT INTO ws_project_quotes (
            project_id,
            quote_number,
            branch,
            prefix,
            quote_date,
            amount,
            quote_status,
            erp_user
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    project_id,
                    clean_number,
                    branch.strip() if branch else None,
                    clean_prefix,
                    quote_date or None,
                    amount,
                    quote_status.strip()
                    if quote_status
                    else None,
                    erp_user.strip()
                    if erp_user
                    else None,
                ),
            )
            conn.commit()

            return int(cursor.lastrowid)

    @staticmethod
    def replace_primary_quote(
        *,
        project_id: int,
        quote_number: str | None,
        prefix: str = "CTC",
        quote_date: str | None = None,
        amount: float | None = None,
        quote_status: str | None = None,
    ) -> None:
        clean_number = (
            quote_number.strip().replace(",", "")
            if quote_number
            else ""
        )

        clean_prefix = prefix.strip().upper() or "CTC"

        with get_connection() as conn:
            conn.execute(
                """
                DELETE FROM ws_project_quotes
                WHERE project_id = ?
                """,
                (project_id,),
            )

            if clean_number:
                conn.execute(
                    """
                    INSERT INTO ws_project_quotes (
                        project_id,
                        quote_number,
                        prefix,
                        quote_date,
                        amount,
                        quote_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        clean_number,
                        clean_prefix,
                        quote_date or None,
                        amount,
                        quote_status.strip()
                        if quote_status
                        else None,
                    ),
                )

            conn.commit()

    @staticmethod
    def list_project_quotes(
        project_id: int,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            id,
            project_id,
            quote_number,
            branch,
            prefix,
            quote_date,
            amount,
            quote_status,
            erp_user,
            created_at
        FROM ws_project_quotes
        WHERE project_id = ?
        ORDER BY quote_date DESC, id DESC
        """

        with get_connection() as conn:
            rows = conn.execute(
                sql,
                (project_id,),
            ).fetchall()

        return [dict(row) for row in rows]