import pandas as pd

from app.database.connection import get_connection

def table_exists(table_name: str) -> bool:
    query = """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name = ?
    """

    with get_connection() as conn:
        result = conn.execute(query, (table_name,)).fetchone()

    return result is not None

def read_table(table_name: str) -> pd.DataFrame:
    if not table_exists(table_name):
        raise ValueError(f"Table does not exist: {table_name}")

    with get_connection() as conn:
        return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)


def query(sql: str, params: tuple | None = None) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)
