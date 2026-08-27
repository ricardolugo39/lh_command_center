from typing import Any

from app.database.transaction import connection_scope


VALID_CURRENCIES = {
    "COP",
    "USD",
}


class QuoteRepository:
    @staticmethod
    def get_primary_for_project(project_id: int):
        with connection_scope() as conn:
            row = conn.execute("""
                SELECT * FROM ws_project_quotes WHERE project_id=?
                ORDER BY revision ASC,id ASC LIMIT 1
            """, (project_id,)).fetchone()
            return dict(row) if row else None


    @staticmethod
    def create_quote(
        *,
        project_id: int,
        prefix: str,
        quote_number: str,
        amount: float,
        currency_code: str,
        normalized_amount: float,
        exchange_rate: float | None = None,
        exchange_rate_type: str | None = None,
        branch: str | None = None,
        quote_status: str | None = None,
        quote_date: str | None = None,
        erp_user: str | None = None,
        revision: int = 0,
    ) -> int:

        if currency_code not in VALID_CURRENCIES:
            raise ValueError(
                f"Invalid currency: {currency_code}"
            )

        sql = """
        INSERT INTO ws_project_quotes (

            project_id,

            quote_number,
            prefix,
            branch,

            quote_date,

            amount,
            currency_code,
            exchange_rate,
            exchange_rate_type,
            normalized_amount,

            quote_status,

            erp_user,

            revision

        )
        VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?
        )
        """

        with connection_scope() as conn:

            cursor = conn.execute(
                sql,
                (
                    project_id,

                    quote_number.strip(),
                    prefix.strip(),
                    branch,

                    quote_date,

                    amount,
                    currency_code,
                    exchange_rate,
                    exchange_rate_type,
                    normalized_amount,

                    quote_status,

                    erp_user,

                    revision,
                ),
            )


            return int(cursor.lastrowid)

    @staticmethod
    def next_crm_revision(project_id: int) -> int:
        with connection_scope() as conn:
            row = conn.execute(
                """SELECT COALESCE(MAX(revision),0)+1
                FROM ws_project_quotes
                WHERE project_id=? AND generated_from_crm_lines=1""",
                (project_id,),
            ).fetchone()
        return int(row[0])

    @staticmethod
    def mark_generated_from_crm(
        quote_id: int, *, signature: str
    ) -> None:
        with connection_scope() as conn:
            conn.execute(
                """UPDATE ws_project_quotes SET
                    generated_from_crm_lines=1,
                    source_lines_signature=?,
                    generated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (signature, quote_id),
            )

    @staticmethod
    def latest_crm_generated(project_id: int) -> dict[str, Any] | None:
        with connection_scope() as conn:
            row = conn.execute(
                """SELECT * FROM ws_project_quotes
                WHERE project_id=? AND generated_from_crm_lines=1
                ORDER BY revision DESC,id DESC LIMIT 1""",
                (project_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_quote(
        quote_id: int,
    ) -> dict[str, Any] | None:

        sql = """
        SELECT *
        FROM ws_project_quotes
        WHERE id = ?
        """

        with connection_scope() as conn:

            cursor = conn.execute(
                sql,
                (quote_id,),
            )

            row = cursor.fetchone()

            if row is None:
                return None

            columns = [
                c[0]
                for c in cursor.description
            ]

            return dict(
                zip(
                    columns,
                    row,
                )
            )

    @staticmethod
    def list_project_quotes(
        project_id: int,
    ) -> list[dict[str, Any]]:

        sql = """
        SELECT *
        FROM ws_project_quotes
        WHERE project_id = ?
        ORDER BY revision ASC
        """

        with connection_scope() as conn:

            cursor = conn.execute(
                sql,
                (project_id,),
            )

            rows = cursor.fetchall()

            columns = [
                c[0]
                for c in cursor.description
            ]

            return [
                dict(zip(columns, row))
                for row in rows
            ]

    @staticmethod
    def update_amount(
        *,
        quote_id: int,
        amount: float,
        normalized_amount: float,
    ) -> None:

        sql = """
        UPDATE ws_project_quotes
        SET
            amount = ?,
            normalized_amount = ?
        WHERE id = ?
        """

        with connection_scope() as conn:

            conn.execute(
                sql,
                (
                    amount,
                    normalized_amount,
                    quote_id,
                ),
            )


    @staticmethod
    def update_exchange_rate(
        *,
        quote_id: int,
        exchange_rate: float,
        exchange_rate_type: str,
        normalized_amount: float,
    ) -> None:

        sql = """
        UPDATE ws_project_quotes
        SET
            exchange_rate = ?,
            exchange_rate_type = ?,
            normalized_amount = ?
        WHERE id = ?
        """

        with connection_scope() as conn:

            conn.execute(
                sql,
                (
                    exchange_rate,
                    exchange_rate_type,
                    normalized_amount,
                    quote_id,
                ),
            )


    @staticmethod
    def update_status(
        *,
        quote_id: int,
        quote_status: str,
    ) -> None:

        sql = """
        UPDATE ws_project_quotes
        SET
            quote_status = ?
        WHERE id = ?
        """

        with connection_scope() as conn:

            conn.execute(
                sql,
                (
                    quote_status,
                    quote_id,
                ),
            )


    @staticmethod
    def create_revision(
        *,
        quote_id: int,
        new_revision: int,
    ) -> None:

        sql = """
        UPDATE ws_project_quotes
        SET
            revision = ?
        WHERE id = ?
        """

        with connection_scope() as conn:

            conn.execute(
                sql,
                (
                    new_revision,
                    quote_id,
                ),
            )


    @staticmethod
    def update_quote_details(
        *,
        quote_id: int,
        prefix: str,
        quote_number: str,
        quote_date: str | None,
        amount: float,
        currency_code: str,
        exchange_rate: float | None,
        exchange_rate_type: str | None,
        normalized_amount: float,
        quote_status: str | None,
    ) -> None:
        sql = """
        UPDATE ws_project_quotes
        SET
            prefix = ?,
            quote_number = ?,
            quote_date = ?,
            amount = ?,
            currency_code = ?,
            exchange_rate = ?,
            exchange_rate_type = ?,
            normalized_amount = ?,
            quote_status = ?
        WHERE id = ?
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (
                    prefix.strip().upper(),
                    quote_number.strip(),
                    quote_date or None,
                    amount,
                    currency_code.strip().upper(),
                    exchange_rate,
                    exchange_rate_type,
                    normalized_amount,
                    quote_status.strip()
                    if quote_status
                    else None,
                    quote_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Quote does not exist: {quote_id}"
                )
