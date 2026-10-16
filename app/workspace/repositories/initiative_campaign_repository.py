from typing import Any

from app.database.transaction import connection_scope


class InitiativeCampaignRepository:

    @staticmethod
    def list_customers(initiative_id: int) -> list[dict[str, Any]]:
        with connection_scope() as conn:
            cursor = conn.execute(
                """
                SELECT *
                FROM ws_initiative_campaign_customers
                WHERE initiative_id = ?
                ORDER BY
                    CASE priority WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 ELSE 3 END,
                    customer_name
                """,
                (initiative_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def upsert_customer(initiative_id: int, customer: dict[str, Any]) -> None:
        with connection_scope() as conn:
            conn.execute(
                """
                INSERT INTO ws_initiative_campaign_customers (
                    initiative_id, customer_erp_id, customer_name, city, advisor,
                    priority, brands, competitor_linear_brands, last_purchase,
                    other_sales, status, source_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(initiative_id, customer_erp_id) DO UPDATE SET
                    customer_name = excluded.customer_name,
                    city = excluded.city,
                    advisor = excluded.advisor,
                    priority = excluded.priority,
                    brands = excluded.brands,
                    competitor_linear_brands = excluded.competitor_linear_brands,
                    last_purchase = excluded.last_purchase,
                    other_sales = excluded.other_sales,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    initiative_id,
                    customer["customer_erp_id"],
                    customer["customer_name"],
                    customer.get("city"),
                    customer["advisor"],
                    customer.get("priority") or "Media",
                    customer.get("brands"),
                    customer.get("competitor_linear_brands"),
                    customer.get("last_purchase"),
                    float(customer.get("other_sales") or 0),
                    customer.get("status") or "Pendiente",
                    customer["source_key"],
                ),
            )

    @staticmethod
    def update_tracking(
        initiative_id: int,
        source_key: str,
        values: dict[str, Any],
    ) -> bool:
        with connection_scope() as conn:
            cursor = conn.execute(
                """
                UPDATE ws_initiative_campaign_customers
                SET status = ?, contact_date = ?, contact_name = ?,
                    application = ?, installed_reference = ?, interest = ?,
                    next_action = ?, next_action_date = ?,
                    opportunity_decision = ?, synced_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE initiative_id = ? AND source_key = ?
                """,
                (
                    values.get("status") or "Pendiente",
                    values.get("contact_date"),
                    values.get("contact_name"),
                    values.get("application"),
                    values.get("installed_reference"),
                    values.get("interest"),
                    values.get("next_action"),
                    values.get("next_action_date"),
                    values.get("opportunity_decision"),
                    initiative_id,
                    source_key,
                ),
            )
            return cursor.rowcount == 1
