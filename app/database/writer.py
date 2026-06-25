import pandas as pd

from app.database.connection import get_connection

def save_dataframe(df: pd.DataFrame, table_name: str, if_exists: str = "replace") -> None:
    if df is None:
        raise ValueError("DataFrame cannot be None")

    with get_connection() as conn:
        df.to_sql(table_name, conn, if_exists=if_exists, index=False)

def execute(sql: str, params: tuple | None = None) -> None:
    with get_connection() as conn:
        conn.execute(sql, params or ())
        conn.commit()