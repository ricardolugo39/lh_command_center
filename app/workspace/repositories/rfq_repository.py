from typing import Any

from app.database.transaction import connection_scope
from app.workspace.constants.commercial_office import sql_office_case


class RFQRepository:
    @staticmethod
    def next_number() -> str:
        with connection_scope() as connection:
            value = connection.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM rfqs"
            ).fetchone()[0]
        return f"RFQ-{int(value):06d}"

    @staticmethod
    def create(values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO rfqs (
                    rfq_number, customer_id, contact_id, owner_user_id,
                    received_at, required_by, status, description,
                    estimated_value, currency_code, opportunity_id,
                    next_action, next_action_at, expected_decision_at,
                    prequotation_number, prequotation_number_normalized,
                    workflow_status
                    , sales_rep_name, vendor_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    values["rfq_number"], values["customer_id"],
                    values.get("contact_id"), values["owner_user_id"],
                    values["received_at"], values.get("required_by"),
                    values["status"], values["description"],
                    values.get("estimated_value"), values.get("currency_code"),
                    values.get("opportunity_id"),
                    # Compatibility values for the legacy RFQ table CHECK.
                    # The current workflow does not ask for or validate these.
                    "Flujo de precotización", values["received_at"], None,
                    values["prequotation_number"],
                    values["prequotation_number_normalized"],
                    values["workflow_status"],
                    values["sales_rep_name"],
                    values.get("vendor_message"),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def add_item(rfq_id: int, values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO rfq_items (
                    rfq_id, product_id, description, quantity,
                    unit_of_measure, quoted_unit_price, currency_code,
                    reference, brand, notes, display_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rfq_id, values.get("product_id"), values["description"],
                    values.get("quantity"), values.get("unit_of_measure"),
                    values.get("quoted_unit_price"), values.get("currency_code"),
                    values["reference"], values["brand"], values.get("notes"),
                    values.get("display_order", 0),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def add_history(
        rfq_id: int, from_status: str | None, to_status: str,
        changed_by_user_id: int, comment: str | None = None,
    ) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO rfq_status_history (
                    rfq_id, from_status, to_status,
                    changed_by_user_id, comment
                ) VALUES (?, ?, ?, ?, ?)""",
                (rfq_id, from_status, to_status, changed_by_user_id, comment),
            )

    @staticmethod
    def get(rfq_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT r.*, c.name AS customer_name,
                    ct.full_name AS contact_name,
                    COALESCE(r.sales_rep_name,u.display_name) AS owner_name,
                    u.email AS owner_email,
                    p.name AS opportunity_name
                FROM rfqs r JOIN ws_customers c ON c.id = r.customer_id
                LEFT JOIN contacts ct ON ct.id = r.contact_id
                JOIN ws_users u ON u.id = r.owner_user_id
                LEFT JOIN ws_projects p ON p.id = r.opportunity_id
                WHERE r.id = ?""",
                (rfq_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_all(
        status: str | None = None, search: str | None = None,
        office: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("r.workflow_status = ?")
            params.append(status)
        if search:
            clauses.append(
                "(r.prequotation_number LIKE ? OR c.name LIKE ? OR EXISTS ("
                "SELECT 1 FROM rfq_items si WHERE si.rfq_id=r.id "
                "AND (si.reference LIKE ? OR si.brand LIKE ?)))"
            )
            params.extend((f"%{search}%",) * 4)
        if office in {"Bogotá", "Cali"}:
            clauses.append(f"{sql_office_case('r.sales_rep_name')} = ?")
            params.append(office)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with connection_scope() as connection:
            rows = connection.execute(
                f"""SELECT r.*, c.name AS customer_name,
                    COALESCE(r.sales_rep_name,u.display_name) AS owner_name,
                    (SELECT COUNT(*) FROM rfq_items i WHERE i.rfq_id=r.id)
                        AS item_count,
                    (SELECT GROUP_CONCAT(DISTINCT i.brand) FROM rfq_items i
                        WHERE i.rfq_id=r.id) AS vendor_summary,
                    (SELECT GROUP_CONCAT(i.reference, ', ') FROM rfq_items i
                        WHERE i.rfq_id=r.id) AS reference_summary,
                    (SELECT COUNT(*) FROM rfq_vendor_requests vr
                        WHERE vr.rfq_id=r.id) AS vendor_request_count,
                    (SELECT COUNT(*) FROM rfq_vendor_requests vr
                        WHERE vr.rfq_id=r.id AND vr.status='responded')
                        AS vendor_response_count
                FROM rfqs r JOIN ws_customers c ON c.id = r.customer_id
                JOIN ws_users u ON u.id = r.owner_user_id
                {where}
                ORDER BY r.closed_at IS NOT NULL, r.next_action_at, r.id DESC""",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_items(rfq_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM rfq_items WHERE rfq_id = ?
                ORDER BY display_order, id""",
                (rfq_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def add_document(rfq_id: int, values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO rfq_documents(
                    rfq_id,original_filename,stored_filename,mime_type,
                    size_bytes,uploaded_by_user_id
                ) VALUES (?,?,?,?,?,?)""",
                (
                    rfq_id, values["original_filename"],
                    values["stored_filename"], values.get("mime_type"),
                    values["size_bytes"], values.get("uploaded_by_user_id"),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def list_documents(rfq_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM rfq_documents
                WHERE rfq_id=? AND is_active=1 ORDER BY uploaded_at,id""",
                (rfq_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def update_vendor_message(rfq_id: int, message: str | None) -> None:
        with connection_scope() as connection:
            connection.execute(
                """UPDATE rfqs SET vendor_message=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (message, rfq_id),
            )

    @staticmethod
    def delete(rfq_id: int) -> None:
        with connection_scope() as connection:
            cursor = connection.execute("DELETE FROM rfqs WHERE id=?", (rfq_id,))
            if cursor.rowcount == 0:
                raise ValueError("La RFQ no existe.")

    @staticmethod
    def update_vendor_response(item_id: int, values: dict[str, Any]) -> None:
        with connection_scope() as connection:
            cursor = connection.execute(
                """UPDATE rfq_items SET vendor_response_status=?,fob_unit_usd=?,
                unit_weight_kg=?,lead_time=?,availability=?,vendor_comments=?,
                vendor_valid_until=?,vendor_responded_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (
                    values["vendor_response_status"], values.get("fob_unit_usd"),
                    values.get("unit_weight_kg"), values.get("lead_time"),
                    values.get("availability"), values.get("vendor_comments"),
                    values.get("vendor_valid_until"), item_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("La línea RFQ no existe.")

    @staticmethod
    def list_history(rfq_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT h.*, u.display_name AS changed_by
                FROM rfq_status_history h
                JOIN ws_users u ON u.id = h.changed_by_user_id
                WHERE h.rfq_id = ? ORDER BY h.changed_at DESC, h.id DESC""",
                (rfq_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def update_status(
        rfq_id: int, status: str, workflow_status: str,
        opportunity_id: int | None = None,
        cancellation_reason: str | None = None,
    ) -> None:
        with connection_scope() as connection:
            connection.execute(
                """UPDATE rfqs SET status = ?, workflow_status = ?,
                    opportunity_id = COALESCE(?, opportunity_id),
                    cancellation_reason = COALESCE(?, cancellation_reason),
                    last_activity_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    sent_at = CASE WHEN ? = 'sent'
                        THEN COALESCE(sent_at, CURRENT_TIMESTAMP) ELSE sent_at END,
                    closed_at = CASE WHEN ? IN (
                        'closed','cancelled'
                    ) THEN CURRENT_TIMESTAMP ELSE NULL END
                WHERE id = ?""",
                (
                    status, workflow_status, opportunity_id,
                    cancellation_reason, workflow_status, workflow_status,
                    rfq_id,
                ),
            )

    @staticmethod
    def list_customer(customer_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT r.*, u.display_name AS owner_name
                FROM rfqs r JOIN ws_users u ON u.id = r.owner_user_id
                WHERE r.customer_id = ?
                ORDER BY r.created_at DESC, r.id DESC""",
                (customer_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def conclude(rfq_id: int, values: dict[str, Any]) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO rfq_conclusions (
                    rfq_id, outcome, reason, final_value, currency_code,
                    erp_sale_reference, opportunity_id, concluded_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rfq_id, values["outcome"], values.get("reason"),
                    values.get("final_value"), values.get("currency_code"),
                    values.get("erp_sale_reference"),
                    values.get("opportunity_id"),
                    values["concluded_by_user_id"],
                ),
            )

    @staticmethod
    def get_conclusion(rfq_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM rfq_conclusions WHERE rfq_id = ?", (rfq_id,)
            ).fetchone()
        return dict(row) if row else None
