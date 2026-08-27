from typing import Any

from app.database.transaction import connection_scope
from app.workspace.product_reference import normalize_product_reference


class AskContextRepository:
    @staticmethod
    def customer_candidates(tokens: list[str], limit: int = 8) -> list[dict]:
        clean = [token for token in tokens if len(token) >= 4][:12]
        if not clean:
            return []
        clauses = " OR ".join(
            "UPPER(c.name) LIKE ?" for _ in clean
        )
        parameters = tuple(f"%{token.upper()}%" for token in clean)
        with connection_scope() as connection:
            has_dimension = AskContextRepository._table_exists(
                connection, "dim_customer"
            )
            join = (
                """LEFT JOIN dim_customer d
                    ON TRIM(d.customer_id)=TRIM(c.erp_customer_id)"""
                if has_dimension else ""
            )
            site_count = (
                "COUNT(d.customer_site_id)" if has_dimension else "0"
            )
            rows = connection.execute(
                f"""SELECT c.id,c.name,c.erp_customer_id,
                    {site_count} AS site_count
                FROM ws_customers c {join}
                WHERE {clauses}
                GROUP BY c.id,c.name,c.erp_customer_id
                ORDER BY c.name LIMIT ?""",
                parameters + (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def customer(customer_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT id,name,erp_customer_id FROM ws_customers
                WHERE id=?""", (customer_id,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def customer_sites(erp_customer_id: str) -> list[dict]:
        with connection_scope() as connection:
            if not AskContextRepository._table_exists(
                connection, "dim_customer"
            ):
                return []
            rows = connection.execute(
                """SELECT customer_site_id,city,address,seller
                FROM dim_customer WHERE TRIM(customer_id)=TRIM(?)
                ORDER BY city,address""", (erp_customer_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def brand_candidates(tokens: list[str]) -> list[str]:
        clean = {token.upper() for token in tokens if len(token) >= 2}
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT brand AS value FROM ws_project_brands
                UNION SELECT supplier FROM ws_agreements
                WHERE supplier IS NOT NULL AND TRIM(supplier)<>''"""
            ).fetchall()
        values = sorted({str(row[0]).strip() for row in rows if row[0]})
        matches = []
        for value in values:
            normalized = value.upper()
            words = set(normalized.replace("-", " ").split())
            if any(
                token == normalized
                or (len(token) >= 3 and token in words)
                for token in clean
            ):
                matches.append(value)
        return matches[:8]

    @staticmethod
    def sales_for_context(
        erp_customer_id: str | None, references: list[str],
        period_months: int,
    ) -> list[dict]:
        clauses = ["date(fecha)>=date('now', ?)"]
        params: list[Any] = [f"-{period_months} months"]
        if erp_customer_id:
            clauses.append(
                "REPLACE(REPLACE(REPLACE(TRIM(nit),'.',''),'-',''),',','')=?"
            )
            params.append(erp_customer_id)
        normalized_references = list(dict.fromkeys(
            normalize_product_reference(reference)
            for reference in references[:500]
            if normalize_product_reference(reference)
        ))
        if normalized_references:
            placeholders = ",".join("?" for _ in normalized_references)
            clauses.append(
                f"NORMALIZE_PRODUCT_REFERENCE(idproducto) IN ({placeholders})"
            )
            params.extend(normalized_references)
        with connection_scope() as connection:
            if not AskContextRepository._table_exists(
                connection, "raw_sales"
            ):
                return []
            AskContextRepository._register_reference_normalizer(connection)
            rows = connection.execute(
                f"""SELECT NORMALIZE_PRODUCT_REFERENCE(idproducto) AS reference,
                    GROUP_CONCAT(DISTINCT TRIM(idproducto))
                        AS source_references,
                    MAX(nombreproducto) AS product_name,
                    SUM(COALESCE(cantidad,0)) AS quantity,
                    SUM(COALESCE(neto,valorbruto,0)) AS revenue,
                    SUM(COALESCE(costo,0)) AS cost,
                    MIN(fecha) AS first_date,MAX(fecha) AS last_date
                FROM raw_sales WHERE {' AND '.join(clauses)}
                GROUP BY NORMALIZE_PRODUCT_REFERENCE(idproducto)
                ORDER BY revenue DESC LIMIT 1000""", tuple(params)
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def sales_evidence_diagnostics(
        erp_customer_id: str | None, references: list[str],
        period_months: int,
    ) -> dict[str, Any]:
        with connection_scope() as connection:
            if not AskContextRepository._table_exists(
                connection, "raw_sales"
            ):
                return {
                    "source_available": False,
                    "all_time_customer_records": 0,
                    "period_customer_records": 0,
                    "matched_reference_records": 0,
                }
            AskContextRepository._register_reference_normalizer(connection)
            customer_clause = ""
            customer_params: list[Any] = []
            if erp_customer_id:
                customer_clause = (
                    " AND REPLACE(REPLACE(REPLACE("
                    "TRIM(nit),'.',''),'-',''),',','')=?"
                )
                customer_params.append(erp_customer_id)
            all_time = connection.execute(
                f"""SELECT COUNT(*) FROM raw_sales
                WHERE 1=1{customer_clause}""",
                tuple(customer_params),
            ).fetchone()[0]
            period_params = [
                f"-{period_months} months", *customer_params,
            ]
            period_count = connection.execute(
                f"""SELECT COUNT(*) FROM raw_sales
                WHERE date(fecha)>=date('now',?){customer_clause}""",
                tuple(period_params),
            ).fetchone()[0]
            matched = period_count
            normalized_references = list(dict.fromkeys(
                normalize_product_reference(reference)
                for reference in references[:500]
                if normalize_product_reference(reference)
            ))
            if normalized_references:
                placeholders = ",".join(
                    "?" for _ in normalized_references
                )
                matched = connection.execute(
                    f"""SELECT COUNT(*) FROM raw_sales
                    WHERE date(fecha)>=date('now',?){customer_clause}
                      AND NORMALIZE_PRODUCT_REFERENCE(idproducto)
                          IN ({placeholders})""",
                    tuple(period_params) + tuple(normalized_references),
                ).fetchone()[0]
        return {
            "source_available": True,
            "all_time_customer_records": int(all_time),
            "period_customer_records": int(period_count),
            "matched_reference_records": int(matched),
        }

    @staticmethod
    def customer_commercial_records(
        customer_id: int, period_months: int | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        since = f"-{period_months} months" if period_months else None
        with connection_scope() as connection:
            opportunities = connection.execute(
                """SELECT id,name,status,objective,current_blocker,sales_rep,
                    commercial_amount,commercial_currency,created_at,updated_at,
                    closed_at,close_reason
                FROM ws_projects WHERE customer_id=?
                ORDER BY updated_at DESC,id DESC LIMIT 100""",
                (customer_id,),
            ).fetchall()
            activity_period = (
                "AND date(a.occurred_at)>=date('now',?)"
                if since else ""
            )
            activity_params = (
                (customer_id, customer_id, since)
                if since else (customer_id, customer_id)
            )
            activities = connection.execute(
                f"""SELECT a.id,a.activity_type,a.title,a.details,a.summary,
                    a.purpose,a.identified_need,a.identified_risk,
                    a.occurred_at,a.created_by,p.name AS opportunity_name,
                    COALESCE(u.display_name,a.created_by) AS advisor_name
                FROM ws_activities a
                LEFT JOIN ws_projects p ON p.id=a.project_id
                LEFT JOIN ws_users u ON u.id=a.advisor_user_id
                WHERE (a.customer_id=? OR p.customer_id=?)
                  {activity_period}
                ORDER BY a.occurred_at DESC,a.id DESC LIMIT 200""",
                activity_params,
            ).fetchall()
            agreements = connection.execute(
                """SELECT id,agreement_number,name,status,agreement_type,
                    supplier,annual_target,currency,start_date,end_date,
                    renewal_date,has_consignment
                FROM ws_agreements WHERE customer_id=?
                ORDER BY end_date DESC,id DESC LIMIT 50""",
                (customer_id,),
            ).fetchall()
            rfqs = connection.execute(
                """SELECT id,rfq_number,status,description,estimated_value,
                    currency_code,received_at,required_by,next_action,
                    next_action_at,opportunity_id
                FROM rfqs WHERE customer_id=?
                ORDER BY received_at DESC,id DESC LIMIT 100""",
                (customer_id,),
            ).fetchall()
            quotes = connection.execute(
                """SELECT q.id,q.quote_number,q.quote_date,q.amount,
                    q.normalized_amount,q.currency_code,q.quote_status,
                    p.id AS opportunity_id,p.name AS opportunity_name
                FROM ws_project_quotes q
                JOIN ws_projects p ON p.id=q.project_id
                WHERE p.customer_id=?
                ORDER BY q.quote_date DESC,q.id DESC LIMIT 100""",
                (customer_id,),
            ).fetchall()
        return {
            "opportunities": [dict(row) for row in opportunities],
            "activities": [dict(row) for row in activities],
            "agreements": [dict(row) for row in agreements],
            "rfqs": [dict(row) for row in rfqs],
            "quotes": [dict(row) for row in quotes],
        }

    @staticmethod
    def _table_exists(connection, name: str) -> bool:
        return connection.execute(
            """SELECT 1 FROM sqlite_master
            WHERE type='table' AND name=?""", (name,)
        ).fetchone() is not None

    @staticmethod
    def _register_reference_normalizer(connection) -> None:
        connection.create_function(
            "NORMALIZE_PRODUCT_REFERENCE", 1,
            normalize_product_reference, deterministic=True,
        )
