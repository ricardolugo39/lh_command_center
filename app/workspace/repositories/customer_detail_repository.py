from typing import Any

from app.database.connection import get_connection


class CustomerDetailRepository:

    @staticmethod
    def get_erp_customer_summary(
        erp_customer_id: str,
    ) -> dict[str, Any] | None:
        sql = """
        SELECT
            customer_id,
            MAX(customer_name) AS customer_name,
            COUNT(*) AS site_count,
            MAX(seller) AS seller,
            MAX(classification_name) AS classification_name,
            MAX(commercial_group_name) AS commercial_group_name,
            MAX(has_credit) AS has_credit,
            MAX(credit_limit) AS credit_limit,
            MAX(payment_terms) AS payment_terms
        FROM dim_customer
        WHERE customer_id = ?
        GROUP BY customer_id
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (erp_customer_id.strip(),),
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
    def list_customer_sites(
        erp_customer_id: str,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            customer_site_id,
            customer_id,
            customer_name,
            address,
            city,
            seller,
            has_credit,
            credit_limit,
            payment_terms,
            activity_name,
            classification_name,
            commercial_group_name
        FROM dim_customer
        WHERE customer_id = ?
        ORDER BY
            city,
            address
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (erp_customer_id.strip(),),
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
    def list_customer_projects(
        customer_id: int,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            p.id,
            p.name,
            p.status,
            p.objective,
            p.current_blocker,
            p.sales_rep,
            p.created_at,
            p.updated_at,

            q.prefix,
            q.quote_number,
            q.amount,
            q.currency_code,
            q.exchange_rate,
            q.normalized_amount

        FROM ws_projects AS p

        LEFT JOIN ws_project_quotes AS q
            ON q.id = (
                SELECT q2.id
                FROM ws_project_quotes AS q2
                WHERE q2.project_id = p.id
                ORDER BY q2.id DESC
                LIMIT 1
            )

        WHERE p.customer_id = ?

        ORDER BY
            p.updated_at DESC,
            p.created_at DESC
        """

        with get_connection() as conn:
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
    def get_pipeline_summary(
        customer_id: int,
    ) -> dict[str, Any]:
        sql = """
        SELECT
            COUNT(
                DISTINCT CASE
                    WHEN p.status NOT IN ('won', 'lost')
                    THEN p.id
                END
            ) AS active_project_count,

            COUNT(
                DISTINCT CASE
                    WHEN p.status = 'won'
                    THEN p.id
                END
            ) AS won_project_count,

            COUNT(
                DISTINCT CASE
                    WHEN p.status = 'lost'
                    THEN p.id
                END
            ) AS lost_project_count,

            COALESCE(
                SUM(
                    CASE
                        WHEN p.status NOT IN ('won', 'lost')
                        THEN q.normalized_amount
                        ELSE 0
                    END
                ),
                0
            ) AS open_pipeline_cop

        FROM ws_projects AS p

        LEFT JOIN ws_project_quotes AS q
            ON q.id = (
                SELECT q2.id
                FROM ws_project_quotes AS q2
                WHERE q2.project_id = p.id
                ORDER BY q2.id DESC
                LIMIT 1
            )

        WHERE p.customer_id = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (customer_id,),
            )
            row = cursor.fetchone()

            columns = [
                column[0]
                for column in cursor.description
            ]

            return dict(zip(columns, row))

    @staticmethod
    def get_sales_summary(
        erp_customer_id: str,
    ) -> dict[str, Any]:
        sql = """
        SELECT
            COALESCE(SUM(neto), 0) AS lifetime_sales,
            COALESCE(
                SUM(
                    CASE
                        WHEN date(fecha) >= date(
                            'now',
                            '-12 months'
                        )
                        THEN neto
                        ELSE 0
                    END
                ),
                0
            ) AS sales_last_12_months,

            COALESCE(
                SUM(
                    CASE
                        WHEN strftime(
                            '%Y',
                            date(fecha)
                        ) = strftime(
                            '%Y',
                            'now'
                        )
                        THEN neto
                        ELSE 0
                    END
                ),
                0
            ) AS sales_current_year,

            MAX(date(fecha)) AS last_purchase_date,

            COUNT(
                DISTINCT
                prefijo || '-' || numero
            ) AS document_count

        FROM raw_sales
        WHERE REPLACE(nit, ',', '') = ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (erp_customer_id.strip(),),
            )
            row = cursor.fetchone()

            columns = [
                column[0]
                for column in cursor.description
            ]

            return dict(zip(columns, row))

    @staticmethod
    def list_recent_sales_documents(
        erp_customer_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            prefijo,
            numero,
            date(fecha) AS sale_date,
            MAX(razonsocial) AS customer_name,
            MAX(sucursal) AS branch,
            MAX(idconvenio) AS agreement_id,
            MAX(ordencompra) AS purchase_order,
            SUM(neto) AS net_amount,
            SUM(valorbruto) AS gross_amount,
            SUM(vdescuento) AS discount_amount,
            COUNT(*) AS line_count
        FROM raw_sales
        WHERE REPLACE(nit, ',', '') = ?
        GROUP BY
            prefijo,
            numero,
            date(fecha)
        ORDER BY
            date(fecha) DESC,
            numero DESC
        LIMIT ?
        """

        with get_connection() as conn:
            cursor = conn.execute(
                sql,
                (
                    erp_customer_id.strip(),
                    limit,
                ),
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