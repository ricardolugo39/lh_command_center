import pandas as pd

from app.database.connection import get_connection


def table_exists(table_name: str) -> bool:
    sql = """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name = ?
    """

    with get_connection() as conn:
        result = conn.execute(sql, (table_name,)).fetchone()

    return result is not None


def read_table(table_name: str) -> pd.DataFrame:
    if not table_exists(table_name):
        raise ValueError(f"Table does not exist: {table_name}")

    sql = f"SELECT * FROM {table_name}"

    with get_connection() as conn:
        return pd.read_sql_query(sql, conn)


def read_sql(sql: str, params=None) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(
            sql,
            conn,
            params=params,
        )