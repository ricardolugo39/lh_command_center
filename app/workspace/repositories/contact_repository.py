from typing import Any

from app.database.transaction import connection_scope


class ContactRepository:
    @staticmethod
    def create(values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO contacts (
                    customer_id, full_name, job_title, role, influence,
                    email, phone, notes, created_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    values["customer_id"], values["full_name"],
                    values.get("job_title"), values.get("role"),
                    values.get("influence"), values.get("email"),
                    values.get("phone"), values.get("notes"),
                    values.get("created_by_user_id"),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def get(contact_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_for_customer(customer_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM contacts
                WHERE customer_id = ? AND is_active = 1
                ORDER BY full_name, id""",
                (customer_id,),
            ).fetchall()
        return [dict(row) for row in rows]


class ActivityFormRepository:
    @staticmethod
    def get_customer(customer_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT id, name, erp_customer_id FROM ws_customers WHERE id = ?",
                (customer_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_project(project_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT id, customer_id, name, closed_at FROM ws_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_agreement(agreement_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT id, customer_id, name FROM ws_agreements WHERE id = ?",
                (agreement_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_users() -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT id, display_name, email, email_normalized, role
                FROM ws_users
                WHERE is_active = 1 AND role <> 'system'
                ORDER BY display_name"""
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_sales_users() -> list[dict[str, Any]]:
        """Return the configured active seller list used by RFQs."""
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT id,display_name,email,email_normalized,role
                FROM ws_users WHERE is_active=1
                  AND role IN ('advisor','commercial_management')
                ORDER BY display_name,id"""
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_sales_representatives() -> list[str]:
        """Use the ERP customer master as the source for RFQ seller choices."""
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT DISTINCT TRIM(vendedor) AS name FROM raw_customers
                WHERE TRIM(COALESCE(vendedor,''))<>''
                ORDER BY name COLLATE NOCASE"""
            ).fetchall()
        return [row["name"] for row in rows]

    @staticmethod
    def list_brand_options() -> list[str]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT brand FROM (
                    SELECT TRIM(brand) AS brand FROM ws_project_brands
                    UNION SELECT TRIM(brand) FROM rfq_items
                    UNION SELECT TRIM(brand) FROM imported_commercial_lines
                ) WHERE TRIM(COALESCE(brand,''))<>''
                ORDER BY brand COLLATE NOCASE"""
            ).fetchall()
        return [row["brand"] for row in rows]

    @staticmethod
    def get_user_by_email(email: str) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT * FROM ws_users
                WHERE email_normalized = LOWER(TRIM(?)) LIMIT 1""",
                (email,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_projects(customer_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT id, name, status FROM ws_projects
                WHERE customer_id = ? ORDER BY closed_at IS NOT NULL, name""",
                (customer_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_agreements(customer_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT id, name, status FROM ws_agreements
                WHERE customer_id = ? ORDER BY status = 'active' DESC, name""",
                (customer_id,),
            ).fetchall()
        return [dict(row) for row in rows]
