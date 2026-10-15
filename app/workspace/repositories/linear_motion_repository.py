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
    def segment_options(cls) -> list[str]:
        rows = cls._all("""
            SELECT DISTINCT TRIM(classification_name) name
            FROM dim_customer
            WHERE TRIM(COALESCE(classification_name,''))<>''
            ORDER BY name
        """)
        return [row["name"] for row in rows]

    @classmethod
    def segment_opportunity(cls, segment: str, brand: str) -> dict[str, Any]:
        target_clause, target_params = cls._sales_filter(brand)
        target_expression = (
            f"{cls.SALES_BRAND_SQL} IS NOT NULL {target_clause}"
        )
        params = target_params + (segment,)
        rows = cls._all(f"""
            WITH customers AS (
                SELECT TRIM(customer_id) customer_id,
                       MAX(customer_name) customer_name,
                       MAX(city) city,
                       GROUP_CONCAT(DISTINCT NULLIF(TRIM(seller),'')) advisor,
                       MAX(classification_name) segment
                FROM dim_customer GROUP BY TRIM(customer_id)
            ), activity AS (
                SELECT REPLACE(TRIM(s.nit),',','') customer_id,
                       MAX(s.razonsocial) sales_name,
                       MAX(date(s.fecha)) last_purchase,
                       SUM(COALESCE(s.neto,0)) total_sales,
                       SUM(CASE WHEN {target_expression}
                           THEN COALESCE(s.neto,0) ELSE 0 END) target_sales,
                       SUM(CASE WHEN {cls.SALES_BRAND_SQL} IS NULL
                           THEN COALESCE(s.neto,0) ELSE 0 END) other_sales,
                       GROUP_CONCAT(DISTINCT NULLIF(UPPER(TRIM(s.sufijo)),'')) brands,
                       GROUP_CONCAT(DISTINCT CASE
                           WHEN CAST(s.idfam2 AS INTEGER) IN (1510,1550,1560)
                            AND {cls.SALES_BRAND_SQL} IS NULL
                           THEN NULLIF(UPPER(TRIM(s.sufijo)),'') END) competitor_linear_brands
                FROM raw_sales s
                WHERE date(s.fecha)>=date('now','-12 months')
                  AND date(s.fecha)<=date('now')
                GROUP BY customer_id
            )
            SELECT c.customer_id,
                   COALESCE(NULLIF(TRIM(c.customer_name),''),a.sales_name) name,
                   COALESCE(NULLIF(TRIM(c.city),''),'Sin ciudad') city,
                   COALESCE(NULLIF(TRIM(c.advisor),''),'Sin asesor') advisor,
                   a.last_purchase,a.total_sales,a.target_sales,a.other_sales
                   ,a.brands,a.competitor_linear_brands
            FROM customers c LEFT JOIN activity a USING(customer_id)
            WHERE c.segment=?
            ORDER BY CASE WHEN COALESCE(a.target_sales,0)=0
                               AND COALESCE(a.other_sales,0)>0 THEN 0 ELSE 1 END,
                     COALESCE(a.other_sales,0) DESC
        """, params)
        active = [row for row in rows if row.get("last_purchase")]
        opportunities = [
            row for row in active
            if float(row.get("target_sales") or 0) == 0
            and float(row.get("other_sales") or 0) > 0
        ]
        return {
            "total": len(rows),
            "active": len(active),
            "target_buyers": sum(
                float(row.get("target_sales") or 0) > 0 for row in active
            ),
            "opportunities": len(opportunities),
            "customers": opportunities,
        }

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

    @classmethod
    def diagnostic_breakdown(cls, brand: str, focus: str) -> dict[str, list[dict[str, Any]]]:
        group_id = {"guides": 1550, "screws": 1560}.get(focus)
        if not group_id:
            return {"components": [], "cities": [], "segments": [], "customers": []}
        clause, brand_params = cls._sales_filter(brand)
        params = (group_id,) + brand_params
        totals = """SUM(CASE WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now') THEN COALESCE(s.neto,0) ELSE 0 END) current,
            SUM(CASE WHEN strftime('%Y',date(s.fecha))=strftime('%Y','now','-1 year') AND strftime('%m-%d',date(s.fecha))<=strftime('%m-%d','now') THEN COALESCE(s.neto,0) ELSE 0 END) previous"""
        where = f"{cls.SALES_BRAND_SQL} IS NOT NULL AND CAST(s.idfam2 AS INTEGER)=? {clause}"
        component = ("""CASE WHEN UPPER(s.nombreproducto) LIKE '%RIEL LINEAL%' AND UPPER(s.nombreproducto) LIKE '%GUIA%' THEN 'Conjunto riel + patines' WHEN UPPER(s.nombreproducto) LIKE '%RIEL LINEAL%' THEN 'Rieles' WHEN UPPER(s.nombreproducto) LIKE '%GUIA LINEAL%' THEN 'Patines o guías' ELSE 'Otros productos en la familia ERP' END""" if focus == "guides" else """CASE WHEN UPPER(s.nombreproducto) LIKE '%TORNILLO DE BOLAS%' AND UPPER(s.nombreproducto) LIKE '%TUERCA%' THEN 'Conjunto tornillo + tuerca' WHEN UPPER(s.nombreproducto) LIKE '%TORNILLO DE BOLAS%' THEN 'Tornillos de bolas' WHEN UPPER(s.nombreproducto) LIKE '%TUERCA DE BOLAS%' THEN 'Tuercas de bolas' ELSE 'Otros productos en la familia ERP' END""")
        components = cls._all(f"SELECT {component} name,{totals} FROM raw_sales s WHERE {where} GROUP BY name HAVING current<>0 OR previous<>0 ORDER BY current-previous", params)
        cte = "WITH customers AS (SELECT TRIM(customer_id) customer_id,MAX(city) city,MAX(classification_name) customer_type FROM dim_customer GROUP BY TRIM(customer_id))"
        cities = cls._all(f"{cte} SELECT COALESCE(NULLIF(TRIM(c.city),''),'Sin ciudad') name,{totals} FROM raw_sales s LEFT JOIN customers c ON c.customer_id=REPLACE(TRIM(s.nit),',','') WHERE {where} GROUP BY name HAVING current<>0 OR previous<>0 ORDER BY current-previous LIMIT 10", params)
        segments = cls._all(f"{cte} SELECT COALESCE(NULLIF(TRIM(c.customer_type),''),'Sin clasificar') name,{totals} FROM raw_sales s LEFT JOIN customers c ON c.customer_id=REPLACE(TRIM(s.nit),',','') WHERE {where} GROUP BY name HAVING current<>0 OR previous<>0 ORDER BY current-previous LIMIT 10", params)
        customers = cls._all(f"SELECT REPLACE(TRIM(s.nit),',','') customer_id,MAX(s.razonsocial) name,{totals} FROM raw_sales s WHERE {where} GROUP BY customer_id HAVING current<>0 OR previous<>0 ORDER BY current-previous LIMIT 12", params)
        return {"components": components, "cities": cities, "segments": segments, "customers": customers}
