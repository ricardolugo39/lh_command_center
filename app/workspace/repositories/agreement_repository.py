from typing import Any

from app.database.transaction import connection_scope


class AgreementRepository:
    @staticmethod
    def get_active_for_customer(customer_id: int) -> dict[str, Any] | None:
        with connection_scope() as conn:
            cursor = conn.execute("""
                SELECT * FROM ws_agreements
                WHERE customer_id = ? AND status = 'active'
                ORDER BY updated_at DESC LIMIT 1
            """, (customer_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def expire(agreement_id: int) -> None:
        with connection_scope() as conn:
            conn.execute("""
                UPDATE ws_agreements SET status = 'expired',
                    updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, (agreement_id,))

    @staticmethod
    def create_agreement(
        *,
        customer_id: int,
        name: str,
        status: str,
        agreement_number: str | None = None,
        agreement_type: str | None = None,
        supplier: str | None = None,
        annual_target: float | None = None,
        currency: str = "COP",
        start_date: str | None = None,
        end_date: str | None = None,
        renewal_date: str | None = None,
        has_consignment: bool = False,
        notes: str | None = None,
    ) -> int:
        sql = """
        INSERT INTO ws_agreements (
            customer_id,
            agreement_number,
            name,
            status,
            agreement_type,
            supplier,
            annual_target,
            currency,
            start_date,
            end_date,
            renewal_date,
            has_consignment,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (
                    customer_id,
                    agreement_number.strip()
                    if agreement_number
                    else None,
                    name.strip(),
                    status,
                    agreement_type.strip()
                    if agreement_type
                    else None,
                    supplier.strip()
                    if supplier
                    else None,
                    annual_target,
                    currency.strip().upper(),
                    start_date or None,
                    end_date or None,
                    renewal_date or None,
                    1 if has_consignment else 0,
                    notes.strip()
                    if notes
                    else None,
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def get_agreement(
        agreement_id: int,
    ) -> dict[str, Any] | None:
        sql = """
        SELECT
            id,
            customer_id,
            agreement_number,
            name,
            status,
            agreement_type,
            supplier,
            annual_target,
            currency,
            start_date,
            end_date,
            renewal_date,
            has_consignment,
            notes,
            created_at,
            updated_at
        FROM ws_agreements
        WHERE id = ?
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (agreement_id,),
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
    def list_customer_agreements(
        customer_id: int,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            id,
            customer_id,
            agreement_number,
            name,
            status,
            agreement_type,
            supplier,
            annual_target,
            currency,
            start_date,
            end_date,
            renewal_date,
            has_consignment,
            notes,
            created_at,
            updated_at
        FROM ws_agreements
        WHERE customer_id = ?
        ORDER BY
            CASE status
                WHEN 'active' THEN 1
                WHEN 'renewal' THEN 2
                WHEN 'draft' THEN 3
                WHEN 'expired' THEN 4
                WHEN 'closed' THEN 5
                ELSE 6
            END,
            updated_at DESC
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (customer_id,),
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
    def update_agreement(
        *,
        agreement_id: int,
        name: str,
        status: str,
        agreement_number: str | None = None,
        agreement_type: str | None = None,
        supplier: str | None = None,
        annual_target: float | None = None,
        currency: str = "COP",
        start_date: str | None = None,
        end_date: str | None = None,
        renewal_date: str | None = None,
        has_consignment: bool = False,
        notes: str | None = None,
    ) -> None:
        sql = """
        UPDATE ws_agreements
        SET
            agreement_number = ?,
            name = ?,
            status = ?,
            agreement_type = ?,
            supplier = ?,
            annual_target = ?,
            currency = ?,
            start_date = ?,
            end_date = ?,
            renewal_date = ?,
            has_consignment = ?,
            notes = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """

        with connection_scope() as conn:
            cursor = conn.execute(
                sql,
                (
                    agreement_number.strip()
                    if agreement_number
                    else None,
                    name.strip(),
                    status,
                    agreement_type.strip()
                    if agreement_type
                    else None,
                    supplier.strip()
                    if supplier
                    else None,
                    annual_target,
                    currency.strip().upper(),
                    start_date or None,
                    end_date or None,
                    renewal_date or None,
                    1 if has_consignment else 0,
                    notes.strip()
                    if notes
                    else None,
                    agreement_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    "El convenio no existe."
                )

    @staticmethod
    def delete_agreement(
        agreement_id: int,
    ) -> None:
        with connection_scope() as conn:
            cursor = conn.execute(
                """
                DELETE FROM ws_agreements
                WHERE id = ?
                """,
                (agreement_id,),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    "El convenio no existe."
                )
