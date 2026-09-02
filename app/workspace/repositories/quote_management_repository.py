import json
from typing import Any

from app.database.transaction import connection_scope
from app.workspace.constants.commercial_office import sql_office_case


class QuoteManagementRepository:
    @staticmethod
    def delete_draft(quote_id: int) -> None:
        with connection_scope() as connection:
            cursor = connection.execute(
                "DELETE FROM ws_project_quotes WHERE id=?", (quote_id,)
            )
            if cursor.rowcount == 0:
                raise ValueError("La cotización no existe.")

    @staticmethod
    def active_profile() -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT * FROM dhl_rate_profiles WHERE active=1
                ORDER BY effective_date DESC,id DESC LIMIT 1"""
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def origin_options(profile_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM dhl_country_zones
                WHERE profile_id=? AND active=1
                ORDER BY CASE country_code WHEN 'US' THEN 0 WHEN 'BR' THEN 1 ELSE 2 END,
                    country_name,service_area_name""",
                (profile_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def resolve_zone(
        profile_id: int, country_code: str, service_area_code: str | None
    ) -> dict[str, Any] | None:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM dhl_country_zones
                WHERE profile_id=? AND country_code=? AND active=1""",
                (profile_id, country_code),
            ).fetchall()
        options = [dict(row) for row in rows]
        if not options:
            return None
        if len(options) == 1:
            return options[0]
        return next(
            (row for row in options if row["service_area_code"] == service_area_code),
            None,
        )

    @staticmethod
    def exact_rate(profile_id: int, weight: str, zone: int) -> str | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT rate_usd FROM dhl_weight_rates
                WHERE profile_id=? AND shipment_kind='package'
                  AND CAST(weight_kg AS REAL)=CAST(? AS REAL) AND zone=?""",
                (profile_id, weight, zone),
            ).fetchone()
        return str(row[0]) if row else None

    @staticmethod
    def increment_rate(profile_id: int, weight: str, zone: int):
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT * FROM dhl_increment_rates
                WHERE profile_id=? AND zone=?
                  AND CAST(? AS REAL)>=CAST(from_weight_kg AS REAL)
                  AND CAST(? AS REAL)<=CAST(to_weight_kg AS REAL)
                ORDER BY CAST(from_weight_kg AS REAL) LIMIT 1""",
                (profile_id, zone, weight, weight),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def settings() -> dict[str, str]:
        with connection_scope() as connection:
            rows = connection.execute("SELECT key,value FROM quote_settings").fetchall()
        return {row["key"]: row["value"] for row in rows}

    @staticmethod
    def pricing_rules() -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                "SELECT * FROM quote_pricing_rules WHERE active=1 ORDER BY rule_name"
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def pricing_rule(rule_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM quote_pricing_rules WHERE id=? AND active=1",
                (rule_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def next_rl_number() -> str:
        with connection_scope() as connection:
            rows = connection.execute(
                "SELECT quote_number FROM ws_project_quotes WHERE prefix='RL'"
            ).fetchall()
        values = [int(row[0]) for row in rows if str(row[0]).isdigit()]
        return str(max(values, default=1177) + 1)

    @staticmethod
    def create_from_rfq(rfq: dict[str, Any], actor_user_id: int) -> int:
        number = QuoteManagementRepository.next_rl_number()
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO ws_project_quotes(
                    project_id,customer_id,originating_rfq_id,quote_series_key,
                    quote_number,prefix,quote_date,amount,normalized_amount,
                    quote_status,currency_code,revision,exchange_rate_type,
                    sales_rep_user_id,sales_rep_name,sales_rep_email,
                    rfq_number_snapshot,request_comments_snapshot,validity_days,
                    created_by_user_id
                ) VALUES (?,?,?,?,?,'RL',DATE('now'),0,0,'draft','USD',1,
                    'estimated',?,?,?,?,?,10,?)""",
                (
                    rfq.get("opportunity_id"), rfq["customer_id"], rfq["id"],
                    f"RL:{number}", number, rfq["owner_user_id"],
                    rfq.get("owner_name"), rfq.get("owner_email"),
                    rfq.get("prequotation_number") or rfq["rfq_number"],
                    rfq.get("description"), actor_user_id,
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def copy_rfq_lines(quote_id: int, rfq_id: int) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO ws_quote_lines(
                    quote_id,brand,part_number,description,quantity,unit_price,
                    line_total,currency_code,display_order,source_rfq_item_id,
                    vendor_fob_unit_usd,unit_weight_kg,lead_time,vendor_comments
                ) SELECT ?,brand,reference,description,quantity,0,0,'USD',
                    display_order,id,fob_unit_usd,unit_weight_kg,lead_time,vendor_comments
                FROM rfq_items WHERE rfq_id=? ORDER BY display_order,id""",
                (quote_id, rfq_id),
            )

    @staticmethod
    def copy_rfq_attachments(quote_id: int, rfq_id: int) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO quote_attachment_links(
                    quote_id,rfq_document_id,original_filename,stored_filename,
                    mime_type,size_bytes,uploaded_by_user_id
                ) SELECT ?,id,original_filename,stored_filename,mime_type,
                    size_bytes,uploaded_by_user_id FROM rfq_documents
                WHERE rfq_id=? AND is_active=1""",
                (quote_id, rfq_id),
            )

    @staticmethod
    def get(quote_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT q.*,c.name customer_name,p.name opportunity_name,
                    r.workflow_status rfq_status
                FROM ws_project_quotes q
                LEFT JOIN ws_customers c ON c.id=q.customer_id
                LEFT JOIN ws_projects p ON p.id=q.project_id
                LEFT JOIN rfqs r ON r.id=q.originating_rfq_id
                WHERE q.id=?""",
                (quote_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def lines(quote_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT l.*,r.reference rfq_reference,r.description rfq_description
                FROM ws_quote_lines l LEFT JOIN rfq_items r ON r.id=l.source_rfq_item_id
                WHERE l.quote_id=? ORDER BY l.display_order,l.id""",
                (quote_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def related_to_rfq(rfq_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM ws_project_quotes WHERE originating_rfq_id=?
                ORDER BY quote_series_key,revision DESC,id DESC""", (rfq_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def update_header(quote_id: int, values: dict[str, Any], actor_user_id: int) -> None:
        columns = (
            "origin_country_code", "origin_service_area_code",
            "premium_service", "commercial_comments", "internal_notes",
            "final_dhl_zone", "zone_override_reason", "final_shipping_usd",
            "shipping_override_reason",
        )
        with connection_scope() as connection:
            connection.execute(
                "UPDATE ws_project_quotes SET "
                + ",".join(f"{name}=?" for name in columns)
                + " WHERE id=?",
                tuple(values.get(name) or None for name in columns) + (quote_id,),
            )
            if values.get("zone_override_reason"):
                connection.execute(
                    """UPDATE ws_project_quotes SET zone_overridden_by_user_id=?,
                    zone_overridden_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (actor_user_id, quote_id),
                )
            if values.get("shipping_override_reason"):
                connection.execute(
                    """UPDATE ws_project_quotes SET shipping_overridden_by_user_id=?,
                    shipping_overridden_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (actor_user_id, quote_id),
                )

    @staticmethod
    def update_line(line_id: int, values: dict[str, Any], actor_user_id: int) -> None:
        columns = (
            "vendor_fob_unit_usd", "unit_weight_kg", "lead_time",
            "pricing_rule_id", "pricing_override_value",
            "pricing_override_reason", "internal_notes",
        )
        with connection_scope() as connection:
            connection.execute(
                "UPDATE ws_quote_lines SET "
                + ",".join(f"{name}=?" for name in columns)
                + ",updated_at=CURRENT_TIMESTAMP WHERE id=?",
                tuple(values.get(name) or None for name in columns) + (line_id,),
            )
            if values.get("pricing_override_value"):
                connection.execute(
                    """UPDATE ws_quote_lines SET pricing_overridden_by_user_id=?,
                    pricing_overridden_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (actor_user_id, line_id),
                )

    @staticmethod
    def save_calculation(
        quote_id: int, quote_values: dict[str, Any], line_values: list[dict[str, Any]]
    ) -> None:
        with connection_scope() as connection:
            for line in line_values:
                connection.execute(
                    """UPDATE ws_quote_lines SET unit_price=?,line_total=?,
                    allocated_shipping_usd=?,allocated_customs_usd=?,
                    allocated_bank_fee_usd=?,landed_cost_usd=?,selling_unit_usd=?,
                    profit_usd=?,margin_percent=?,roi_percent=? WHERE id=?""",
                    (
                        line["selling_unit"], line["selling_total"], line["shipping"],
                        line["customs"], line["bank"], line["landed"],
                        line["selling_unit"], line["profit"], line["margin"],
                        line["roi"], line["id"],
                    ),
                )
            fields = tuple(quote_values)
            connection.execute(
                "UPDATE ws_project_quotes SET "
                + ",".join(f"{field}=?" for field in fields) + " WHERE id=?",
                tuple(quote_values[field] for field in fields) + (quote_id,),
            )

    @staticmethod
    def portfolio(filters: dict[str, Any]) -> list[dict[str, Any]]:
        clauses, parameters = [], []
        for key, column in (("status", "q.quote_status"), ("customer", "q.customer_id")):
            if filters.get(key):
                clauses.append(f"{column}=?")
                parameters.append(filters[key])
        if filters.get("brand"):
            clauses.append("EXISTS(SELECT 1 FROM ws_quote_lines l WHERE l.quote_id=q.id AND l.brand=?)")
            parameters.append(filters["brand"])
        if filters.get("office") in {"Bogotá", "Cali"}:
            clauses.append(f"{sql_office_case('q.sales_rep_name')} = ?")
            parameters.append(filters["office"])
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with connection_scope() as connection:
            rows = connection.execute(
                f"""SELECT q.*,c.name customer_name,
                    GROUP_CONCAT(DISTINCT l.brand) brands,
                    GROUP_CONCAT(DISTINCT l.part_number) product_summary,
                    SUM(l.quantity) quantity_summary,
                    (SELECT due_date FROM quote_followups f WHERE f.quote_id=q.id
                     AND f.status='pending' ORDER BY due_date LIMIT 1) next_followup
                FROM ws_project_quotes q
                LEFT JOIN ws_customers c ON c.id=q.customer_id
                LEFT JOIN ws_quote_lines l ON l.quote_id=q.id
                {where} GROUP BY q.id ORDER BY q.quote_date DESC,q.id DESC""",
                tuple(parameters),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def attachments(quote_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                "SELECT * FROM quote_attachment_links WHERE quote_id=? ORDER BY id",
                (quote_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def latest_pdf(quote_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM quote_pdfs WHERE quote_id=? ORDER BY id DESC LIMIT 1",
                (quote_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def save_pdf(quote_id: int, stored_filename: str, actor: int) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO quote_pdfs(quote_id,stored_filename,template_version,
                generated_by_user_id) VALUES (?,?,'1',?)""",
                (quote_id, stored_filename, actor),
            )
        return int(cursor.lastrowid)

    @staticmethod
    def save_delivery(quote_id: int, values: dict[str, Any], actor: int) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO quote_deliveries(quote_id,recipient_email,cc_json,
                subject,body_text,body_html,advisor_note,note_internal_only,
                note_included,attachment_ids_json,prepared_by_user_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    quote_id, values["recipient_email"], json.dumps(values["cc"]),
                    values["subject"], values["body_text"], values["body_html"],
                    values.get("advisor_note"), int(values.get("note_internal_only", True)),
                    int(values.get("note_included", True)),
                    json.dumps(values.get("attachment_ids", [])), actor,
                ),
            )
        return int(cursor.lastrowid)

    @staticmethod
    def add_attachment(quote_id: int, values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO quote_attachment_links(quote_id,original_filename,
                stored_filename,mime_type,size_bytes,category,uploaded_by_user_id,
                included_in_delivery,vendor_confidential) VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    quote_id,values["original_filename"],values["stored_filename"],
                    values.get("mime_type"),values.get("size_bytes"),values.get("category","other"),
                    values.get("uploaded_by_user_id"),int(values.get("included_in_delivery",False)),
                    int(values.get("vendor_confidential",False)),
                ),
            )
        return int(cursor.lastrowid)

    @staticmethod
    def get_delivery(delivery_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM quote_deliveries WHERE id=?", (delivery_id,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def latest_delivery(quote_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM quote_deliveries WHERE quote_id=? ORDER BY id DESC LIMIT 1",
                (quote_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def mark_delivery_sent(delivery_id: int, result: dict[str, Any], actor: int) -> None:
        with connection_scope() as connection:
            connection.execute(
                """UPDATE quote_deliveries SET status='sent',provider_message_id=?,
                provider_thread_id=?,sent_by_user_id=?,sent_at=CURRENT_TIMESTAMP,last_error=NULL
                WHERE id=?""", (result.get("message_id"),result.get("thread_id"),actor,delivery_id)
            )

    @staticmethod
    def mark_delivery_error(delivery_id: int, error: str) -> None:
        with connection_scope() as connection:
            connection.execute(
                "UPDATE quote_deliveries SET status='failed',last_error=? WHERE id=?",
                (error, delivery_id),
            )
