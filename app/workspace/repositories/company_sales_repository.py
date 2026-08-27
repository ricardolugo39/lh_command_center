from typing import Any

from app.database.connection import get_connection
from app.workspace.constants.commercial_office import sql_office_case


class CompanySalesRepository:
    """Read model for Lugo Hermanos consolidated and office sales."""

    @staticmethod
    def list_history(office: str = "", months: int = 24) -> list[dict[str, Any]]:
        single_office_case = sql_office_case("customers.seller")
        resolved_office = (
            "CASE WHEN branch.office IS NOT NULL THEN branch.office "
            f"WHEN customers.seller_count=1 THEN {single_office_case} "
            "ELSE 'Sin atribuir' END"
        )
        office_filter = f"AND {resolved_office} = ?" if office else ""
        params: tuple[Any, ...] = (
            (f"-{int(months)} months", office) if office
            else (f"-{int(months)} months",)
        )
        sql = f"""
        WITH customers AS (
            SELECT customer_id, MAX(customer_name) customer_name,
                   MAX(seller) seller,
                   COUNT(DISTINCT seller) seller_count
            FROM dim_customer
            GROUP BY customer_id
        ), branch AS (
            SELECT customer_id,branch_code,customer_site_id,site_label,
                   city,sales_rep,office,mapping_status
            FROM erp_customer_branch_mappings
        ), families AS (
            SELECT family_id, MAX(family_name) family_name
            FROM dim_product_category GROUP BY family_id
        )
        SELECT date(s.fecha) sale_date, s.prefijo, s.numero,
               s.idproducto product_id, s.nombreproducto product_name,
               s.cantidad, s.neto,
               COALESCE(f.family_name,'Sin clasificar') family_name,
               REPLACE(s.nit,',','') customer_id,
               COALESCE(customers.customer_name,s.razonsocial,'Sin cliente') customer_name,
               CASE WHEN branch.sales_rep IS NOT NULL THEN branch.sales_rep
                    WHEN customers.seller_count=1 THEN customers.seller
                    ELSE 'MULTISEDE · SIN MAPEAR' END sales_rep,
               {resolved_office} office,
               s.sucursal branch_code,
               branch.customer_site_id,
               branch.site_label,
               branch.city site_city,
               CASE WHEN branch.mapping_status IS NOT NULL THEN branch.mapping_status
                    WHEN customers.seller_count=1 THEN 'single_owner'
                    ELSE 'unmapped_multisite' END attribution_status
        FROM raw_sales s
        LEFT JOIN customers ON customers.customer_id=REPLACE(s.nit,',','')
        LEFT JOIN branch ON branch.customer_id=REPLACE(s.nit,',','')
            AND TRIM(branch.branch_code)=TRIM(CAST(s.sucursal AS TEXT))
        LEFT JOIN families f ON CAST(f.family_id AS REAL)=s.idfam1
        WHERE date(s.fecha)>=date('now',?) AND date(s.fecha)<=date('now')
          {office_filter}
        ORDER BY date(s.fecha),s.prefijo,s.numero
        """
        with get_connection() as connection:
            cursor = connection.execute(sql, params)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
