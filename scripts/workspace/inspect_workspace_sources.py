from app.database.connection import get_connection


TABLES_TO_INSPECT = [
    "dim_customer",
    "raw_customers",
    "raw_crm",
    "fact_crm",
    "raw_quotes",
    "fact_quotes",
]


def table_exists(conn, table_name: str) -> bool:
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


def print_table_schema(conn, table_name: str) -> None:
    print("\n" + "=" * 80)
    print(table_name)
    print("=" * 80)

    if not table_exists(conn, table_name):
        print("TABLE DOES NOT EXIST")
        return

    columns = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    print("\nColumns")
    print("-" * 80)

    for column in columns:
        print(
            f"{column['name']} | "
            f"{column['type']} | "
            f"not_null={column['notnull']} | "
            f"pk={column['pk']}"
        )

    count = conn.execute(
        f"SELECT COUNT(*) AS row_count FROM {table_name}"
    ).fetchone()["row_count"]

    print(f"\nRows: {count:,}")

    if count == 0:
        return

    rows = conn.execute(
        f"SELECT * FROM {table_name} LIMIT 5"
    ).fetchall()

    print("\nPreview")
    print("-" * 80)

    for row in rows:
        print(dict(row))


def find_candidate_columns(conn) -> None:
    print("\n" + "=" * 80)
    print("CANDIDATE SALES REP / QUOTE COLUMNS")
    print("=" * 80)

    candidate_terms = [
        "vendedor",
        "asesor",
        "responsable",
        "comercial",
        "sales",
        "rep",
        "quote",
        "cotizacion",
        "cotización",
        "numero",
        "valor",
        "marca",
    ]

    tables = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
        """
    ).fetchall()

    for table in tables:
        table_name = table["name"]

        columns = conn.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()

        matches = [
            column["name"]
            for column in columns
            if any(
                term in column["name"].lower()
                for term in candidate_terms
            )
        ]

        if matches:
            print(f"{table_name}: {matches}")


def main() -> None:
    with get_connection() as conn:
        for table_name in TABLES_TO_INSPECT:
            print_table_schema(conn, table_name)

        find_candidate_columns(conn)


if __name__ == "__main__":
    main()