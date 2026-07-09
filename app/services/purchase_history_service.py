import pandas as pd

from app.database.reader import query


class PurchaseHistoryService:

    @staticmethod
    def get_history(
        customer: str,
        family_id: str | None = None,
        group_id: str | None = None,
        months: int = 18,
    ) -> pd.DataFrame:

        sql = """
        SELECT
            s.idproducto AS part_number,
            s.nombreproducto AS description,
            SUBSTR(TRIM(s.idproducto), -3) AS brand,
            SUM(CAST(s.cantidad AS REAL)) AS qty,
            COUNT(DISTINCT s.numero) AS orders,
            SUM(CAST(s.valorbruto AS REAL)) AS sales,
            MAX(s.fecha) AS last_purchase
        FROM raw_sales s
        WHERE
            UPPER(s.razonsocial)=UPPER(?)
            AND s.fecha >= (
                SELECT date(MAX(fecha), '-' || ? || ' months')
                FROM raw_sales
            )
        """

        params = [customer, months]

        if family_id:
            sql += "\nAND s.idfam1=?"
            params.append(str(family_id))

        if group_id:
            sql += "\nAND s.idfam2=?"
            params.append(str(group_id))

        sql += """
        GROUP BY
            s.idproducto,
            s.nombreproducto

        ORDER BY
            qty DESC,
            sales DESC
        """

        return query(sql, tuple(params))