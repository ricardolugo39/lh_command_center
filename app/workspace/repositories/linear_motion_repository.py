from typing import Any

from app.database.connection import get_connection


class LinearMotionRepository:
    """Read model for THK and Thomson commercial intelligence."""

    SALES_BRAND_SQL = (
        "CASE WHEN UPPER(TRIM(s.sufijo)) = 'THK' THEN 'THK' "
        "WHEN UPPER(TRIM(s.sufijo)) IN ('THO','THOMSON') "
        "THEN 'Thomson' END"
    )
    INVENTORY_BRAND_SQL = (
        "CASE WHEN UPPER(TRIM(i.marca_codigo)) = 'THK' THEN 'THK' "
        "WHEN UPPER(TRIM(i.marca_codigo)) IN ('THO','THOMSON') "
        "OR UPPER(TRIM(i.marca_nombre)) LIKE '%THOMSON%' "
        "THEN 'Thomson' END"
    )

    @staticmethod
    def _all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with get_connection() as connection:
            cursor = connection.execute(sql, params)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @staticmethod
    def _one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
        rows = LinearMotionRepository._all(sql, params)
        return rows[0] if rows else {}

    @classmethod
    def _sales_filter(cls, brand: str) -> tuple[str, tuple[Any, ...]]:
        if brand in {"THK", "Thomson"}:
            return f"AND {cls.SALES_BRAND_SQL} = ?", (brand,)
        return "", ()

    @classmethod
    def _inventory_filter(cls, brand: str) -> tuple[str, tuple[Any, ...]]:
        if brand in {"THK", "Thomson"}:
            return f"AND {cls.INVENTORY_BRAND_SQL} = ?", (brand,)
        return "", ()

    @classmethod
    def sales_summary(cls, brand: str) -> dict[str, Any]:
        clause, params = cls._sales_filter(brand)
        return cls._one(f"""
            SELECT COALESCE(SUM(CASE
                       WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now')
                       AND date(s.fecha)<=date('now') THEN s.neto ELSE 0 END),0) sales_ytd,
                   COALESCE(SUM(CASE
                       WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now','-1 year')
                       AND strftime('%m-%d',date(s.fecha))<=strftime('%m-%d','now')
                       THEN s.neto ELSE 0 END),0) sales_previous_ytd,
                   COUNT(DISTINCT CASE
                       WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now')
                       THEN REPLACE(s.nit,',','') END) active_customers,
                   COUNT(DISTINCT CASE
                       WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now')
                       THEN s.idproducto END) active_products,
                   COUNT(DISTINCT CASE
                       WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now')
                       THEN s.prefijo||'-'||s.numero END) documents,
                   MIN(date(s.fecha)) first_sale, MAX(date(s.fecha)) last_sale
            FROM raw_sales s
            WHERE {cls.SALES_BRAND_SQL} IS NOT NULL {clause}
        """, params)

    @classmethod
    def monthly_sales(cls, brand: str) -> list[dict[str, Any]]:
        clause, params = cls._sales_filter(brand)
        return cls._all(f"""
            SELECT strftime('%Y-%m',date(s.fecha)) month,
                   {cls.SALES_BRAND_SQL} brand,
                   SUM(COALESCE(s.neto,0)) sales
            FROM raw_sales s
            WHERE {cls.SALES_BRAND_SQL} IS NOT NULL
              AND date(s.fecha)>=date('now','-23 months','start of month')
              AND date(s.fecha)<=date('now') {clause}
            GROUP BY month,brand ORDER BY month,brand
        """, params)

    @classmethod
    def family_sales(cls, brand: str) -> list[dict[str, Any]]:
        clause, params = cls._sales_filter(brand)
        return cls._all(f"""
            WITH groups AS (
                SELECT CAST(grupo AS REAL) group_id,MAX(denominación) group_name
                FROM dim_product GROUP BY CAST(grupo AS REAL)
            )
            SELECT {cls.SALES_BRAND_SQL} brand,
                   COALESCE(g.group_name,'Sin clasificar') family,
                   SUM(CASE WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now')
                       THEN COALESCE(s.neto,0) ELSE 0 END) sales_ytd,
                   SUM(CASE WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now','-1 year')
                       AND strftime('%m-%d',date(s.fecha))<=strftime('%m-%d','now')
                       THEN COALESCE(s.neto,0) ELSE 0 END) sales_previous_ytd,
                   COUNT(DISTINCT CASE WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now')
                       THEN s.idproducto END) products
            FROM raw_sales s LEFT JOIN groups g ON g.group_id=CAST(s.idfam2 AS REAL)
            WHERE {cls.SALES_BRAND_SQL} IS NOT NULL {clause}
            GROUP BY brand,family
            HAVING sales_ytd<>0 OR sales_previous_ytd<>0
            ORDER BY sales_ytd DESC
        """, params)

    @classmethod
    def city_sales(cls, brand: str) -> list[dict[str, Any]]:
        clause, params = cls._sales_filter(brand)
        return cls._all(f"""
            WITH customers AS (
                SELECT TRIM(customer_id) customer_id,MAX(city) city
                FROM dim_customer GROUP BY TRIM(customer_id)
            )
            SELECT {cls.SALES_BRAND_SQL} brand,
                   COALESCE(NULLIF(TRIM(c.city),''),'Sin ciudad') city,
                   SUM(COALESCE(s.neto,0)) sales,
                   COUNT(DISTINCT REPLACE(TRIM(s.nit),',','')) customers
            FROM raw_sales s LEFT JOIN customers c
              ON c.customer_id=REPLACE(TRIM(s.nit),',','')
            WHERE {cls.SALES_BRAND_SQL} IS NOT NULL
              AND strftime('%Y',date(s.fecha))=strftime('%Y','now') {clause}
            GROUP BY brand,city ORDER BY sales DESC LIMIT 15
        """, params)

    @classmethod
    def inventory(cls, brand: str) -> list[dict[str, Any]]:
        clause, params = cls._inventory_filter(brand)
        return cls._all(f"""
            SELECT {cls.INVENTORY_BRAND_SQL} brand,
                   MAX(i.fecha_snapshot) snapshot_date,
                   COUNT(DISTINCT i.idproducto) products,
                   SUM(COALESCE(i.unidades_disponible,0)) available,
                   SUM(COALESCE(i.unidades_reservado,0)) reserved,
                   SUM(COALESCE(i.unidades_transito,0)) transit,
                   SUM(COALESCE(i.valor_total,0)) inventory_value
            FROM inventario_snapshot i
            WHERE i.fecha_snapshot=(SELECT MAX(fecha_snapshot) FROM inventario_snapshot)
              AND {cls.INVENTORY_BRAND_SQL} IS NOT NULL {clause}
            GROUP BY brand ORDER BY brand
        """, params)

    @classmethod
    def customer_coverage(cls, brand: str) -> dict[str, Any]:
        clause, params = cls._sales_filter(brand)
        return cls._one(f"""
            WITH buyers AS (
                SELECT DISTINCT REPLACE(TRIM(s.nit),',','') customer_id
                FROM raw_sales s WHERE {cls.SALES_BRAND_SQL} IS NOT NULL {clause}
            ), customers AS (
                SELECT TRIM(customer_id) customer_id,MAX(city) city,
                       MAX(activity_name) activity_name,
                       MAX(classification_name) classification_name
                FROM dim_customer GROUP BY TRIM(customer_id)
            )
            SELECT COUNT(*) buyers,
                   SUM(TRIM(COALESCE(c.city,''))<>'') with_city,
                   SUM(TRIM(COALESCE(c.activity_name,''))<>'') with_activity,
                   SUM(TRIM(COALESCE(c.classification_name,''))<>'') with_classification
            FROM buyers b LEFT JOIN customers c USING(customer_id)
        """, params)

    @classmethod
    def customer_segments(cls, brand: str) -> list[dict[str, Any]]:
        clause, params = cls._sales_filter(brand)
        return cls._all(f"""
            WITH customers AS (
                SELECT TRIM(customer_id) customer_id,
                       MAX(classification_name) customer_type
                FROM dim_customer GROUP BY TRIM(customer_id)
            )
            SELECT {cls.SALES_BRAND_SQL} brand,
                   COALESCE(NULLIF(TRIM(c.customer_type),''),'Sin clasificar') customer_type,
                   COUNT(DISTINCT REPLACE(TRIM(s.nit),',','')) customers,
                   SUM(COALESCE(s.neto,0)) sales
            FROM raw_sales s LEFT JOIN customers c
              ON c.customer_id=REPLACE(TRIM(s.nit),',','')
            WHERE {cls.SALES_BRAND_SQL} IS NOT NULL
              AND strftime('%Y',date(s.fecha))=strftime('%Y','now') {clause}
            GROUP BY brand,customer_type
            ORDER BY sales DESC
        """, params)

    @classmethod
    def commercial_coverage(cls, brand: str) -> dict[str, Any]:
        values = ("THK", "Thomson") if not brand else (brand,)
        placeholders = ",".join("?" for _ in values)
        return cls._one(f"""
            WITH normalized_lines AS (
                SELECT q.project_id,
                       CASE WHEN UPPER(TRIM(l.brand))='THK' THEN 'THK'
                            WHEN UPPER(TRIM(l.brand)) IN ('THO','THOMSON')
                            THEN 'Thomson' END brand,
                       q.id quote_id
                FROM ws_quote_lines l JOIN ws_project_quotes q ON q.id=l.quote_id
            ), selected AS (
                SELECT * FROM normalized_lines WHERE brand IN ({placeholders})
            )
            SELECT COUNT(DISTINCT quote_id) quotes,
                   COUNT(DISTINCT project_id) linked_projects,
                   (SELECT COUNT(DISTINCT p.id) FROM ws_projects p
                    JOIN ws_project_brands b ON b.project_id=p.id
                    WHERE (CASE WHEN UPPER(TRIM(b.brand))='THK' THEN 'THK'
                                WHEN UPPER(TRIM(b.brand)) IN ('THO','THOMSON')
                                THEN 'Thomson' END) IN ({placeholders})) tagged_projects
            FROM selected
        """, values + values)
