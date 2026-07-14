from typing import Any

from app.database.connection import get_connection


VALID_CURRENCIES = {
    "COP",
    "USD",
}


class QuoteRepository:

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

        with get_connection() as conn:

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

            conn.commit()

            return int(cursor.lastrowid)

    @staticmethod
    def get_quote(
        quote_id: int,
    ) -> dict[str, Any] | None:

        sql = """
        SELECT *
        FROM ws_project_quotes
        WHERE id = ?
        """

        with get_connection() as conn:

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

        with get_connection() as conn:

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

        with get_connection() as conn:

            conn.execute(
                sql,
                (
                    amount,
                    normalized_amount,
                    quote_id,
                ),
            )

            conn.commit()

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

        with get_connection() as conn:

            conn.execute(
                sql,
                (
                    exchange_rate,
                    exchange_rate_type,
                    normalized_amount,
                    quote_id,
                ),
            )

            conn.commit()

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

        with get_connection() as conn:

            conn.execute(
                sql,
                (
                    quote_status,
                    quote_id,
                ),
            )

            conn.commit()

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

        with get_connection() as conn:

            conn.execute(
                sql,
                (
                    new_revision,
                    quote_id,
                ),
            )

            conn.commit()

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

        with get_connection() as conn:
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

            conn.commit()