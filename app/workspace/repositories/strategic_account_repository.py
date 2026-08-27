from typing import Any

from app.database.connection import get_connection


class StrategicAccountRepository:
    """Persistence queries for the strategic-account dashboard read model."""

    @staticmethod
    def get_account(customer_id: int) -> dict[str, Any] | None:
        sql = """
        SELECT
            c.id,
            c.name,
            c.erp_customer_id,
            MAX(d.seller) AS sales_rep
        FROM ws_customers AS c
        LEFT JOIN dim_customer AS d
            ON d.customer_id = c.erp_customer_id
        WHERE c.id = ?
        GROUP BY c.id, c.name, c.erp_customer_id
        """
        return StrategicAccountRepository._one(sql, (customer_id,))

    @staticmethod
    def get_agreement(customer_id: int) -> dict[str, Any] | None:
        sql = """
        SELECT a.id, a.name, a.status, a.supplier, a.start_date, a.end_date,
            (SELECT COUNT(*) FROM ws_agreement_items i
             WHERE i.agreement_id = a.id) AS item_count
        FROM ws_agreements a
        WHERE a.customer_id = ?
        ORDER BY
            CASE status
                WHEN 'active' THEN 1
                WHEN 'renewal' THEN 2
                WHEN 'draft' THEN 3
                ELSE 4
            END,
            updated_at DESC
        LIMIT 1
        """
        return StrategicAccountRepository._one(sql, (customer_id,))

    @staticmethod
    def get_sales_summary(erp_customer_id: str) -> dict[str, Any]:
        sql = """
        SELECT
            COALESCE(SUM(CASE
                WHEN strftime('%Y', date(fecha)) = strftime('%Y', 'now')
                 AND date(fecha) <= date('now')
                THEN neto ELSE 0 END), 0) AS revenue_ytd,
            COALESCE(SUM(CASE
                WHEN strftime('%Y', date(fecha)) = strftime('%Y', 'now', '-1 year')
                 AND date(fecha) <= date('now', '-1 year')
                THEN neto ELSE 0 END), 0) AS revenue_previous_ytd,
            COUNT(DISTINCT CASE
                WHEN strftime('%Y', date(fecha)) = strftime('%Y', 'now')
                 AND date(fecha) <= date('now')
                THEN prefijo || '-' || numero END) AS sales_documents
        FROM raw_sales
        WHERE REPLACE(nit, ',', '') = ?
        """
        return StrategicAccountRepository._one(
            sql, (erp_customer_id,)
        ) or {
            "revenue_ytd": 0,
            "revenue_previous_ytd": 0,
            "sales_documents": 0,
        }

    @staticmethod
    def list_monthly_sales(erp_customer_id: str) -> list[dict[str, Any]]:
        sql = """
        SELECT
            CAST(strftime('%m', date(fecha)) AS INTEGER) AS month_number,
            CASE
                WHEN strftime('%Y', date(fecha)) = strftime('%Y', 'now')
                THEN 'current' ELSE 'previous'
            END AS period,
            SUM(neto) AS revenue
        FROM raw_sales
        WHERE REPLACE(nit, ',', '') = ?
          AND strftime('%Y', date(fecha)) IN (
              strftime('%Y', 'now'),
              strftime('%Y', 'now', '-1 year')
          )
          AND strftime('%m-%d', date(fecha)) <= strftime('%m-%d', 'now')
        GROUP BY month_number, period
        ORDER BY month_number, period
        """
        return StrategicAccountRepository._all(sql, (erp_customer_id,))

    @staticmethod
    def list_top_product_families(
        erp_customer_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        sql = """
        WITH family_dimension AS (
            SELECT family_id, MAX(family_name) AS family_name
            FROM dim_product_category
            GROUP BY family_id
        )
        SELECT
            COALESCE(pc.family_name, 'Sin clasificar')
                AS family_name,
            SUM(CASE
                WHEN strftime('%Y', date(s.fecha)) = strftime('%Y', 'now')
                 AND date(s.fecha) <= date('now')
                THEN s.neto ELSE 0 END) AS revenue,
            SUM(CASE
                WHEN strftime('%Y', date(s.fecha)) = strftime('%Y', 'now', '-1 year')
                 AND strftime('%m-%d', date(s.fecha)) <= strftime('%m-%d', 'now')
                THEN s.neto ELSE 0 END) AS previous_revenue,
            SUM(SUM(CASE
                WHEN strftime('%Y', date(s.fecha)) = strftime('%Y', 'now')
                 AND date(s.fecha) <= date('now')
                THEN s.neto ELSE 0 END)) OVER () AS total_revenue
        FROM raw_sales AS s
        LEFT JOIN family_dimension AS pc
            ON CAST(pc.family_id AS REAL) = s.idfam1
        WHERE REPLACE(s.nit, ',', '') = ?
          AND strftime('%Y', date(s.fecha)) IN (
              strftime('%Y', 'now'),
              strftime('%Y', 'now', '-1 year')
          )
        GROUP BY COALESCE(pc.family_name, 'Sin clasificar')
        HAVING revenue > 0
        ORDER BY revenue DESC
        """
        return StrategicAccountRepository._all(
            sql, (erp_customer_id,)
        )

    @staticmethod
    def list_top_products(erp_customer_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return StrategicAccountRepository._all(
            """SELECT s.idproducto product_id,MAX(s.nombreproducto) product_name,
                SUM(CASE WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now')
                    THEN s.neto ELSE 0 END) revenue,
                SUM(CASE WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now','-1 year')
                    THEN s.neto ELSE 0 END) previous_revenue,
                MAX(date(s.fecha)) last_purchase_date,SUM(s.cantidad) quantity
            FROM raw_sales s WHERE REPLACE(s.nit,',','')=?
              AND strftime('%Y',date(s.fecha)) IN (strftime('%Y','now'),strftime('%Y','now','-1 year'))
            GROUP BY s.idproducto ORDER BY revenue DESC LIMIT ?""",
            (erp_customer_id, limit),
        )

    @staticmethod
    def list_sales_history(erp_customer_id: str, months: int = 24) -> list[dict[str, Any]]:
        return StrategicAccountRepository._all(
            """WITH family_dimension AS (
                SELECT family_id,MAX(family_name) family_name
                FROM dim_product_category GROUP BY family_id
            )
            SELECT date(s.fecha) sale_date,s.prefijo,s.numero,s.idproducto product_id,
                s.nombreproducto product_name,s.cantidad,s.neto,
                COALESCE(fd.family_name,'Sin clasificar') family_name
            FROM raw_sales s LEFT JOIN family_dimension fd
              ON CAST(fd.family_id AS REAL)=s.idfam1
            WHERE REPLACE(s.nit,',','')=?
              AND date(s.fecha)>=date('now',?) AND date(s.fecha)<=date('now')
            ORDER BY date(s.fecha),s.prefijo,s.numero""",
            (erp_customer_id, f"-{int(months)} months"),
        )

    @staticmethod
    def get_activity_summary(customer_id: int) -> dict[str, Any]:
        sql = """
        SELECT
            (SELECT COUNT(*) FROM ws_commercial_visits v
             WHERE v.customer_id=? AND v.is_active=1) AS visits,
            (SELECT COUNT(*) FROM ws_commercial_visits v
             WHERE v.customer_id=? AND v.is_active=1
               AND LOWER(v.visit_type) LIKE '%técnica%') AS technical_visits,
            (SELECT COUNT(*) FROM ws_project_quotes AS q
             INNER JOIN ws_projects AS p ON p.id = q.project_id
             WHERE p.customer_id = ?) AS quotes,
            (SELECT COUNT(*) FROM ws_projects
             WHERE customer_id = ?) AS opportunities,
            (SELECT COUNT(*) FROM ws_project_files AS f
             INNER JOIN ws_projects AS p ON p.id = f.project_id
             WHERE p.customer_id = ?) AS documents,
            (SELECT MAX(v.visit_date) FROM ws_commercial_visits v
             WHERE v.customer_id=? AND v.is_active=1
               AND date(v.visit_date)<=date('now')) AS last_visit,
            (SELECT MAX(v.visit_date) FROM ws_commercial_visits v
             WHERE v.customer_id=? AND v.is_active=1
               AND date(v.visit_date)<=date('now')) AS last_meaningful_activity,
            (SELECT MAX(v.visit_date) FROM ws_commercial_visits v
             WHERE v.customer_id=? AND v.is_active=1
               AND date(v.visit_date)<=date('now')) AS last_activity,
            (SELECT COUNT(*) FROM ws_commercial_visits v
             WHERE v.customer_id=? AND v.is_active=1 AND v.requires_action=1
               AND v.visit_status<>'Cerrado') AS pending_actions
        """
        return StrategicAccountRepository._one(
            sql, (customer_id,) * 9
        ) or {}

    @staticmethod
    def list_recent_activities(
        customer_id: int,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            a.id,
            a.activity_type,
            a.title,
            a.details,
            a.occurred_at,
            p.id AS project_id,
            p.name AS project_name
        FROM ws_activities AS a
        INNER JOIN ws_projects AS p ON p.id = a.project_id
        WHERE p.customer_id = ?
        ORDER BY
            CASE WHEN a.activity_type IN (
                'visit', 'meeting', 'call', 'email', 'note'
            ) THEN 0 ELSE 1 END,
            a.occurred_at DESC,
            a.id DESC
        LIMIT ?
        """
        return StrategicAccountRepository._all(sql, (customer_id, limit))

    @staticmethod
    def list_opportunities(customer_id: int) -> list[dict[str, Any]]:
        sql = """
        SELECT
            p.id,
            p.name,
            p.status,
            p.sales_rep,
            p.updated_at,
            COALESCE(p.commercial_amount,q.normalized_amount,cp.potential_value,0) AS amount,
            CASE WHEN p.commercial_amount IS NOT NULL THEN 'approved'
                 WHEN q.normalized_amount IS NOT NULL THEN 'quote'
                 WHEN cp.potential_value IS NOT NULL THEN 'crm'
                 ELSE 'none' END AS amount_source
        FROM ws_projects AS p
        LEFT JOIN ws_project_quotes AS q ON q.id = (
            SELECT q2.id FROM ws_project_quotes AS q2
            WHERE q2.project_id = p.id
            ORDER BY q2.id DESC LIMIT 1
        )
        LEFT JOIN (
            SELECT opportunity_id,SUM(potential_value) potential_value
            FROM imported_commercial_lines WHERE is_active=1
            GROUP BY opportunity_id
        ) cp ON cp.opportunity_id=p.id
        WHERE p.customer_id = ? AND p.closed_at IS NULL
        ORDER BY
            CASE WHEN COALESCE(q.normalized_amount, 0) > 0 THEN 0 ELSE 1 END,
            COALESCE(q.normalized_amount, 0) DESC,
            p.updated_at DESC
        """
        return StrategicAccountRepository._all(sql, (customer_id,))

    @staticmethod
    def _one(sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with get_connection() as connection:
            cursor = connection.execute(sql, params)
            row = cursor.fetchone()
            if row is None:
                return None
            return dict(zip((column[0] for column in cursor.description), row))

    @staticmethod
    def _all(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with get_connection() as connection:
            cursor = connection.execute(sql, params)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
