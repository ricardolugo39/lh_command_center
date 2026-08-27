from typing import Any

from app.database.transaction import connection_scope


class CommercialApprovalRepository:
    FIELDS = (
        "manufacturer", "branch", "sales_representative", "product_family",
        "product", "product_reference", "quantity", "competitor", "opportunity_value", "probability",
        "current_stage", "list_price", "requested_price", "requested_discount",
        "estimated_margin", "expected_revenue", "currency", "reason_code",
        "justification", "competitor_price", "competition_notes",
        "commercial_impact", "business_notes", "erp_price_source",
        "erp_price_retrieved_at",
    )

    @staticmethod
    def get_type(code: str) -> dict[str, Any] | None:
        with connection_scope() as conn:
            row = conn.execute(
                "SELECT * FROM ws_approval_types WHERE code=? AND is_active=1", (code,)
            ).fetchone()
            return dict(row) if row else None

    @classmethod
    def create(cls, *, project_id: int, approval_type_id: int,
               customer_name: str, opportunity_name: str, created_by: str,
               values: dict[str, Any]) -> int:
        columns = ",".join(cls.FIELDS)
        placeholders = ",".join("?" for _ in cls.FIELDS)
        params = [values.get(field) for field in cls.FIELDS]
        with connection_scope() as conn:
            cursor = conn.execute(f"""
                INSERT INTO ws_commercial_approvals (
                    project_id,approval_type_id,status,customer_name,
                    opportunity_name,created_by,{columns}
                ) VALUES (?,?, 'draft', ?, ?, ?, {placeholders})
            """, (project_id, approval_type_id, customer_name,
                    opportunity_name, created_by, *params))
            return int(cursor.lastrowid)

    @classmethod
    def update_draft(cls, approval_id: int, values: dict[str, Any]) -> None:
        assignments = ",".join(f"{field}=?" for field in cls.FIELDS)
        with connection_scope() as conn:
            conn.execute(
                f"UPDATE ws_commercial_approvals SET {assignments}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (*[values.get(field) for field in cls.FIELDS], approval_id),
            )

    @staticmethod
    def update_status(approval_id: int, status: str, *, submitted: bool = False) -> None:
        submitted_sql = ", submitted_at=CURRENT_TIMESTAMP" if submitted else ""
        with connection_scope() as conn:
            conn.execute(
                f"UPDATE ws_commercial_approvals SET status=?, updated_at=CURRENT_TIMESTAMP{submitted_sql} WHERE id=?",
                (status, approval_id),
            )

    @staticmethod
    def get(approval_id: int) -> dict[str, Any] | None:
        with connection_scope() as conn:
            row = conn.execute("""
                SELECT a.*, t.code AS type_code, t.name AS type_name,
                    p.customer_id FROM ws_commercial_approvals a
                JOIN ws_approval_types t ON t.id=a.approval_type_id
                JOIN ws_projects p ON p.id=a.project_id
                WHERE a.id=? AND a.soft_deleted_at IS NULL
            """, (approval_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def add_history(*, approval_id: int, event_type: str, actor: str,
                    from_status: str | None, to_status: str | None,
                    comments: str = "", event_data: str | None = None) -> None:
        with connection_scope() as conn:
            conn.execute("""
                INSERT INTO ws_commercial_approval_history (
                    approval_id,event_type,from_status,to_status,actor,comments,event_data
                ) VALUES (?,?,?,?,?,?,?)
            """, (approval_id,event_type,from_status,to_status,actor,comments,event_data))

    @staticmethod
    def add_decision(*, approval_id: int, decision: str, approver: str,
                     comments: str, approved_discount: float | None,
                     expiration_date: str | None,
                     monetary: dict[str, str | None] | None = None) -> None:
        monetary = monetary or {}
        with connection_scope() as conn:
            conn.execute("""
                INSERT INTO ws_commercial_approval_decisions (
                    approval_id,decision,approver,comments,approved_discount,expiration_date,
                    requested_discount_percent,approved_discount_percent,list_unit_price,
                    approved_unit_price,quantity_decimal,approved_total_amount,
                    decision_currency,decision_comments,decided_by
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (approval_id,decision,approver,comments,approved_discount,expiration_date,
                    monetary.get("requested_discount_percent"),
                    monetary.get("approved_discount_percent"),monetary.get("list_unit_price"),
                    monetary.get("approved_unit_price"),monetary.get("quantity"),
                    monetary.get("approved_total_amount"),monetary.get("currency"),
                    comments,approver))

    @staticmethod
    def list_history(approval_id: int) -> list[dict[str, Any]]:
        with connection_scope() as conn:
            return [dict(row) for row in conn.execute("""
                SELECT * FROM ws_commercial_approval_history
                WHERE approval_id=? ORDER BY created_at,id
            """, (approval_id,)).fetchall()]

    @staticmethod
    def list_project_timeline_events(project_id: int) -> list[dict[str, Any]]:
        with connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT
                    h.*,
                    a.project_id,
                    a.requested_discount,
                    a.product_reference,
                    a.product,
                    a.currency
                FROM ws_commercial_approval_history AS h
                JOIN ws_commercial_approvals AS a
                  ON a.id = h.approval_id
                WHERE a.project_id = ?
                  AND a.soft_deleted_at IS NULL
                  AND h.event_type IN (
                      'created', 'submitted', 'approved', 'returned',
                      'rejected', 'cancelled', 'expired'
                  )
                ORDER BY h.created_at DESC, h.id DESC
                """,
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def list_decisions(approval_id: int) -> list[dict[str, Any]]:
        with connection_scope() as conn:
            return [dict(row) for row in conn.execute("""
                SELECT * FROM ws_commercial_approval_decisions
                WHERE approval_id=? ORDER BY decided_at,id
            """, (approval_id,)).fetchall()]

    @staticmethod
    def list_project(project_id: int, *, status: str = "", limit: int = 25,
                     offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        condition = "AND a.status=?" if status else ""
        params = (project_id, status) if status else (project_id,)
        with connection_scope() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM ws_commercial_approvals a WHERE a.project_id=? AND a.soft_deleted_at IS NULL {condition}", params).fetchone()[0]
            rows = conn.execute(f"""
                SELECT a.*,t.name AS type_name,d.approver,d.approved_discount,d.decided_at,
                    d.approved_discount_percent,d.approved_unit_price,d.approved_total_amount,
                    d.decision_currency,d.decision_comments
                FROM ws_commercial_approvals a JOIN ws_approval_types t ON t.id=a.approval_type_id
                LEFT JOIN ws_commercial_approval_decisions d ON d.id=(
                    SELECT id FROM ws_commercial_approval_decisions WHERE approval_id=a.id ORDER BY id DESC LIMIT 1)
                WHERE a.project_id=? AND a.soft_deleted_at IS NULL {condition}
                ORDER BY a.updated_at DESC,a.id DESC LIMIT ? OFFSET ?
            """, (*params,limit,offset)).fetchall()
            return [dict(row) for row in rows], int(total)

    @staticmethod
    def get_metrics(project_id: int) -> dict[str, Any]:
        with connection_scope() as conn:
            row = conn.execute("""
                SELECT SUM(status='pending_approval') pending,
                    SUM(status='approved') approved,SUM(status='rejected') rejected,
                    AVG(CASE WHEN status='approved' THEN COALESCE(
                        (SELECT approved_discount FROM ws_commercial_approval_decisions d
                         WHERE d.approval_id=ws_commercial_approvals.id
                           AND d.decision='approved' ORDER BY d.id DESC LIMIT 1),
                        requested_discount) END) average_discount,
                    AVG(CASE WHEN status IN ('approved','rejected')
                        THEN (julianday(updated_at)-julianday(submitted_at))*24 END) average_hours
                FROM ws_commercial_approvals WHERE project_id=? AND soft_deleted_at IS NULL
            """, (project_id,)).fetchone()
            return dict(row)

    @staticmethod
    def get_latest(project_id: int) -> dict[str, Any] | None:
        with connection_scope() as conn:
            row = conn.execute("""
                SELECT a.*,d.approver,d.approved_discount,d.comments latest_comments,
                    d.approved_discount_percent,d.approved_unit_price,d.approved_total_amount,
                    d.decision_currency,d.decision_comments,d.decided_at
                FROM ws_commercial_approvals a
                LEFT JOIN ws_commercial_approval_decisions d ON d.id=(SELECT id FROM ws_commercial_approval_decisions WHERE approval_id=a.id ORDER BY id DESC LIMIT 1)
                WHERE a.project_id=? AND a.soft_deleted_at IS NULL
                ORDER BY a.updated_at DESC,a.id DESC LIMIT 1
            """, (project_id,)).fetchone()
            return dict(row) if row else None
