from typing import Any

from app.database.transaction import connection_scope
from app.workspace.agreement_reference import sql_normalize_product_reference
from app.workspace.policies.customer_portfolio_status_policy import (
    CustomerPortfolioStatusPolicy,
)
from app.workspace.constants.quote_status import OPEN_QUOTE_STATUSES_SQL
from app.workspace.constants.commercial_office import OFFICES, sql_office_case


class CustomerPortfolioRepository:
    """Persistence read model sourced from the ERP customer master."""

    BASE_CTE = f"""
    WITH master AS (
        SELECT TRIM(customer_id) AS erp_customer_id,
            MAX(customer_name) AS customer_name,
            MAX(seller) AS sales_rep,
            MAX(city) AS city
        FROM dim_customer
        WHERE TRIM(COALESCE(customer_id, '')) <> ''
        GROUP BY TRIM(customer_id)
    ), contacts AS (
        SELECT REPLACE(TRIM(nit), ',', '') AS erp_customer_id,
            MAX(COALESCE(NULLIF(email, ''), NULLIF(emailfe, ''))) AS contact_email,
            MAX(COALESCE(NULLIF(movil, ''), NULLIF(telefono1, ''))) AS contact_phone,
            GROUP_CONCAT(COALESCE(email, '') || ' ' || COALESCE(emailfe, '') || ' ' || COALESCE(movil, '') || ' ' || COALESCE(telefono1, ''), ' ') AS contact_search
        FROM raw_customers
        WHERE TRIM(COALESCE(nit, '')) <> ''
        GROUP BY REPLACE(TRIM(nit), ',', '')
    ), sales AS (
        SELECT REPLACE(nit, ',', '') AS erp_customer_id,
            SUM(CASE WHEN strftime('%Y', date(fecha)) = strftime('%Y', 'now')
                AND date(fecha) <= date('now') THEN COALESCE(neto, 0) ELSE 0 END) AS revenue_ytd,
            SUM(CASE WHEN strftime('%Y', date(fecha)) = strftime('%Y', 'now', '-1 year')
                AND date(fecha) <= date('now', '-1 year') THEN COALESCE(neto, 0) ELSE 0 END) AS revenue_ly
            ,MAX(date(fecha)) AS last_purchase_date
        FROM raw_sales
        GROUP BY REPLACE(nit, ',', '')
    ), project_stats AS (
        SELECT customer_id,
            SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) AS open_opportunities,
            MAX(updated_at) AS last_project_at
        FROM ws_projects GROUP BY customer_id
    ), activity_stats AS (
        SELECT p.customer_id, MAX(a.occurred_at) AS last_activity_at
        FROM ws_activities a JOIN ws_projects p ON p.id = a.project_id
        GROUP BY p.customer_id
    ), quote_stats AS (
        SELECT p.customer_id,
            MAX(COALESCE(q.quote_date, q.created_at)) AS last_quote_at,
            SUM(CASE WHEN p.closed_at IS NULL AND LOWER(COALESCE(q.quote_status,''))
                IN ({OPEN_QUOTE_STATUSES_SQL}) THEN 1 ELSE 0 END) AS open_quotes
        FROM ws_project_quotes q JOIN ws_projects p ON p.id = q.project_id
        GROUP BY p.customer_id
    ), visit_stats AS (
        SELECT customer_id, MAX(visit_date) AS last_visit_at,
            SUM(strftime('%Y',visit_date)=strftime('%Y','now')) AS visits_ytd
        FROM ws_commercial_visits
        WHERE customer_id IS NOT NULL AND is_active=1
        GROUP BY customer_id
    ), followup_stats AS (
        SELECT p.customer_id, MIN(f.due_date) AS next_followup_date,
            (SELECT f2.description FROM ws_followups f2
             JOIN ws_projects p2 ON p2.id = f2.project_id
             WHERE p2.customer_id = p.customer_id AND f2.status = 'pending'
             ORDER BY f2.due_date, f2.id LIMIT 1) AS next_followup
        FROM ws_followups f JOIN ws_projects p ON p.id = f.project_id
        WHERE f.status = 'pending' GROUP BY p.customer_id
    ), agreement_stats AS (
        SELECT customer_id, COUNT(*) AS active_agreements,
            MAX(name) AS agreement_name, MAX(id) AS agreement_id
        FROM ws_agreements WHERE status = 'active' GROUP BY customer_id
    ), portfolio AS (
        SELECT m.erp_customer_id, m.customer_name, m.sales_rep, m.city,
            ct.contact_email, ct.contact_phone, ct.contact_search,
            {sql_office_case('m.sales_rep')} AS office,
            COALESCE(NULLIF(meta.advisor, ''), 'Sin asignar') AS advisor,
            COALESCE(meta.is_strategic, 0) AS is_strategic,
            w.id AS workspace_id,
            COALESCE(s.revenue_ytd, 0) AS revenue_ytd,
            COALESCE(s.revenue_ly, 0) AS revenue_ly,
            s.last_purchase_date,
            COALESCE(ps.open_opportunities, 0) AS open_opportunities,
            COALESCE(qs.open_quotes, 0) AS open_quotes,
            MAX(COALESCE(ast.last_activity_at, ''),
                COALESCE(vs.last_visit_at, ''),
                COALESCE(qs.last_quote_at, ''),
                COALESCE(ps.last_project_at, '')) AS last_activity,
            vs.last_visit_at, COALESCE(vs.visits_ytd,0) AS visits_ytd,
            fs.next_followup_date, fs.next_followup,
            COALESCE(ags.active_agreements, 0) AS active_agreements,
            ags.agreement_name, ags.agreement_id
        FROM master m
        LEFT JOIN contacts ct ON ct.erp_customer_id = m.erp_customer_id
        LEFT JOIN ws_customer_portfolio_metadata meta
            ON meta.erp_customer_id = m.erp_customer_id
        LEFT JOIN ws_customers w ON w.erp_customer_id = m.erp_customer_id
        LEFT JOIN sales s ON s.erp_customer_id = m.erp_customer_id
        LEFT JOIN project_stats ps ON ps.customer_id = w.id
        LEFT JOIN activity_stats ast ON ast.customer_id = w.id
        LEFT JOIN visit_stats vs ON vs.customer_id = w.id
        LEFT JOIN quote_stats qs ON qs.customer_id = w.id
        LEFT JOIN followup_stats fs ON fs.customer_id = w.id
        LEFT JOIN agreement_stats ags ON ags.customer_id = w.id
    )
    """

    FILTERS = {
        "strategic": "is_strategic = 1",
        "agreement": "active_agreements > 0",
        "no_agreement": "active_agreements = 0",
        "risk": CustomerPortfolioStatusPolicy.RISK_SQL,
        "inactive": CustomerPortfolioStatusPolicy.INACTIVE_SQL,
        "opportunities": "open_opportunities > 0",
        "no_sales": "revenue_ytd = 0",
    }
    SORTS = {
        "name": "customer_name COLLATE NOCASE",
        "sales": "revenue_ytd",
        "growth": "CASE WHEN revenue_ly > 0 THEN (revenue_ytd-revenue_ly)/revenue_ly ELSE NULL END",
        "activity": "last_activity",
        "opportunities": "open_opportunities",
        "purchase": "last_purchase_date",
        "state": CustomerPortfolioStatusPolicy.STATE_SORT_SQL,
    }

    @classmethod
    def get_assignment(cls, erp_customer_id: str) -> dict[str, Any] | None:
        with connection_scope() as conn:
            row = conn.execute("""
                SELECT office,advisor,is_strategic
                FROM ws_customer_portfolio_metadata WHERE erp_customer_id=?
            """, (erp_customer_id,)).fetchone()
            return dict(row) if row else None

    @classmethod
    def get_master_customer(cls, erp_customer_id: str) -> dict[str, Any] | None:
        with connection_scope() as conn:
            row = conn.execute(
                """SELECT TRIM(customer_id) AS erp_customer_id,
                    MAX(customer_name) AS customer_name
                FROM dim_customer WHERE TRIM(customer_id) = ?
                GROUP BY TRIM(customer_id)""",
                (erp_customer_id.strip(),),
            ).fetchone()
            return dict(row) if row else None

    @classmethod
    def list_portfolio(cls, *, search: str, quick_filter: str, office: str,
                       advisor: str, sort: str, direction: str,
                       limit: int, offset: int) -> list[dict[str, Any]]:
        where, params = cls._where(search, quick_filter, office, advisor)
        order = cls.SORTS.get(sort, cls.SORTS["state"])
        direction = "ASC" if direction == "asc" else "DESC"
        sql = f"{cls.BASE_CTE} SELECT *, COUNT(*) OVER() AS filtered_total FROM portfolio {where} ORDER BY {order} {direction}, customer_name COLLATE NOCASE LIMIT ? OFFSET ?"
        with connection_scope() as conn:
            rows = conn.execute(sql, (*params, limit, offset)).fetchall()
            return [dict(row) for row in rows]

    @classmethod
    def get_statistics(cls, *, search: str = "", quick_filter: str = "",
                       office: str = "", advisor: str = "") -> dict[str, Any]:
        where, params = cls._where(search, quick_filter, office, advisor)
        sql = f"""{cls.BASE_CTE}
        SELECT COUNT(*) AS total,
            SUM(is_strategic = 1) AS strategic,
            SUM(active_agreements > 0) AS agreement,
            SUM(active_agreements = 0) AS no_agreement,
            SUM(last_purchase_date IS NULL OR date(last_purchase_date) < date('now','-60 days')) AS inactive_purchase,
            SUM({CustomerPortfolioStatusPolicy.INACTIVE_SQL}) AS inactive,
            SUM({CustomerPortfolioStatusPolicy.RISK_SQL}) AS risk,
            SUM(open_opportunities > 0) AS opportunities,
            SUM(revenue_ytd = 0) AS no_sales,
            SUM(open_opportunities) AS open_opportunities,
            SUM(revenue_ytd) AS revenue_ytd
        FROM portfolio {where}"""
        with connection_scope() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row)

    @classmethod
    def get_dimensions(cls) -> dict[str, list[str]]:
        sql = """
        WITH master AS (
            SELECT TRIM(customer_id) AS erp_customer_id,
                MAX(seller) AS sales_rep, MAX(city) AS city
            FROM dim_customer WHERE TRIM(COALESCE(customer_id,'')) <> ''
            GROUP BY TRIM(customer_id)
        ), dimensions AS (
            SELECT COALESCE(NULLIF(meta.advisor,''), 'Sin asignar') AS advisor
            FROM master m LEFT JOIN ws_customer_portfolio_metadata meta
                ON meta.erp_customer_id = m.erp_customer_id
        )
        SELECT 'advisor' AS dimension, advisor AS value FROM dimensions GROUP BY advisor
        ORDER BY dimension, value COLLATE NOCASE
        """
        with connection_scope() as conn:
            rows = conn.execute(sql).fetchall()
        return {
            "offices": list(OFFICES),
            "advisors": [row["value"] for row in rows if row["dimension"] == "advisor" and row["value"]],
        }

    @staticmethod
    def sync_metadata_from_master() -> None:
        with connection_scope() as conn:
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ws_customer_portfolio_metadata'"
            ).fetchone():
                return
            conn.execute("""
                INSERT INTO ws_customer_portfolio_metadata (
                    erp_customer_id, is_strategic, branch, office, advisor
                )
                SELECT TRIM(customer_id), 0,
                    CASE WHEN UPPER(MAX(COALESCE(seller,''))) LIKE '%CALI%'
                         THEN 'Cali' ELSE 'Bogotá' END,
                    CASE WHEN UPPER(MAX(COALESCE(seller,''))) LIKE '%CALI%'
                         THEN 'Cali' ELSE 'Bogotá' END,
                    COALESCE(NULLIF(MAX(seller),''), 'Sin asignar')
                FROM dim_customer
                WHERE TRIM(COALESCE(customer_id,'')) <> ''
                GROUP BY TRIM(customer_id)
                ON CONFLICT(erp_customer_id) DO UPDATE SET
                    branch = COALESCE(NULLIF(ws_customer_portfolio_metadata.branch,''), excluded.branch),
                    office = COALESCE(NULLIF(ws_customer_portfolio_metadata.office,''), excluded.office),
                    advisor = COALESCE(NULLIF(ws_customer_portfolio_metadata.advisor,''), excluded.advisor),
                    updated_at = CURRENT_TIMESTAMP
            """)

    @staticmethod
    def get_coverage(agreement_ids: list[int]) -> dict[int, dict[str, int]]:
        if not agreement_ids:
            return {}
        placeholders = ",".join("?" for _ in agreement_ids)
        normalize_sale = sql_normalize_product_reference("s.idproducto")
        normalize_item = sql_normalize_product_reference(
            "COALESCE(NULLIF(i.manufacturer_part_number,''),NULLIF(i.internal_sku,''),i.part_number)"
        )
        sql = f"""
        WITH target AS (
            SELECT a.id AS agreement_id, a.supplier, c.erp_customer_id
            FROM ws_agreements a JOIN ws_customers c ON c.id = a.customer_id
            WHERE a.id IN ({placeholders})
        ), customer_sales AS (
            SELECT DISTINCT t.agreement_id, {normalize_sale} AS product_key
            FROM target t JOIN raw_sales s
                ON REPLACE(s.nit, ',', '') = t.erp_customer_id
            WHERE strftime('%Y', date(s.fecha)) = strftime('%Y', 'now')
              AND date(s.fecha) <= date('now')
        )
        SELECT t.agreement_id, COUNT(DISTINCT i.id) AS negotiated,
            COUNT(DISTINCT CASE WHEN s.product_key IS NOT NULL THEN i.id END) AS purchased
        FROM target t JOIN ws_agreement_items i ON i.agreement_id = t.agreement_id
        LEFT JOIN customer_sales s ON s.agreement_id = t.agreement_id
            AND (s.product_key = {normalize_item}
                OR s.product_key = {normalize_item} || UPPER(REPLACE(COALESCE(t.supplier,''),' ','')))
        GROUP BY t.agreement_id
        """
        with connection_scope() as conn:
            rows = conn.execute(sql, agreement_ids).fetchall()
            return {row["agreement_id"]: dict(row) for row in rows}

    @classmethod
    def _where(cls, search: str, quick_filter: str, office: str, advisor: str):
        clauses, params = [], []
        if search.strip():
            clauses.append("(customer_name LIKE ? OR erp_customer_id LIKE ? OR COALESCE(contact_search,'') LIKE ? OR COALESCE(sales_rep,'') LIKE ?)")
            pattern = f"%{search.strip()}%"
            params.extend((pattern, pattern, pattern, pattern))
        if quick_filter in cls.FILTERS:
            clauses.append(cls.FILTERS[quick_filter])
        if office:
            clauses.append("office = ?")
            params.append(office)
        if advisor:
            clauses.append("advisor = ?")
            params.append(advisor)
        return ("WHERE " + " AND ".join(clauses) if clauses else ""), tuple(params)
