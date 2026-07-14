from sqlite3 import Connection

from app.database.connection import get_connection


TABLE_NAME = "ws_project_quotes"


def table_exists(
    conn: Connection,
    table_name: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def column_exists(
    conn: Connection,
    table_name: str,
    column_name: str,
) -> bool:
    columns = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        column["name"] == column_name
        for column in columns
    )


def add_column_if_missing(
    conn: Connection,
    *,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    if column_exists(
        conn,
        table_name,
        column_name,
    ):
        print(
            f"✓ {table_name}.{column_name} already exists"
        )
        return

    conn.execute(
        f"""
        ALTER TABLE {table_name}
        ADD COLUMN {column_name} {column_definition}
        """
    )

    print(
        f"✓ Added {table_name}.{column_name}"
    )


def migrate_quote_domain(
    conn: Connection,
) -> None:
    if not table_exists(conn, TABLE_NAME):
        raise RuntimeError(
            f"Required table does not exist: {TABLE_NAME}"
        )

    add_column_if_missing(
        conn,
        table_name=TABLE_NAME,
        column_name="currency_code",
        column_definition="TEXT NOT NULL DEFAULT 'COP'",
    )

    add_column_if_missing(
        conn,
        table_name=TABLE_NAME,
        column_name="exchange_rate",
        column_definition="REAL",
    )

    add_column_if_missing(
        conn,
        table_name=TABLE_NAME,
        column_name="normalized_amount",
        column_definition="REAL",
    )

    add_column_if_missing(
        conn,
        table_name=TABLE_NAME,
        column_name="revision",
        column_definition="INTEGER NOT NULL DEFAULT 0",
    )

    conn.execute(
        """
        UPDATE ws_project_quotes
        SET currency_code = 'COP'
        WHERE currency_code IS NULL
           OR TRIM(currency_code) = ''
        """
    )

    conn.execute(
        """
        UPDATE ws_project_quotes
        SET normalized_amount = amount
        WHERE currency_code = 'COP'
          AND normalized_amount IS NULL
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_ws_project_quotes_project_id
        ON ws_project_quotes(project_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_ws_project_quotes_currency
        ON ws_project_quotes(currency_code)
        """
    )


def main() -> None:
    print("=" * 72)
    print("Migrating Quote Domain")
    print("=" * 72)

    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        migrate_quote_domain(conn)

        conn.commit()

    print("=" * 72)
    print("✅ Quote Domain migration completed")
    print("=" * 72)


if __name__ == "__main__":
    main()