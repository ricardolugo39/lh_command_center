from app.database.connection import get_connection


def column_exists(
    conn,
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


def add_sales_rep_column(conn) -> None:
    if column_exists(
        conn,
        "ws_projects",
        "sales_rep",
    ):
        print("✓ ws_projects.sales_rep already exists")
        return

    conn.execute(
        """
        ALTER TABLE ws_projects
        ADD COLUMN sales_rep TEXT
        """
    )

    print("✓ Added ws_projects.sales_rep")


def create_project_quotes_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ws_project_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            project_id INTEGER NOT NULL,

            quote_number TEXT NOT NULL,

            branch TEXT,

            prefix TEXT NOT NULL,

            quote_date TEXT,

            amount REAL,

            quote_status TEXT,

            erp_user TEXT,

            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id)
                REFERENCES ws_projects(id)
                ON DELETE CASCADE,

            UNIQUE (
                project_id,
                prefix,
                quote_number
            )
        )
        """
    )

    print("✓ ws_project_quotes ready")


def create_project_brands_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ws_project_brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            project_id INTEGER NOT NULL,

            brand TEXT NOT NULL,

            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id)
                REFERENCES ws_projects(id)
                ON DELETE CASCADE,

            UNIQUE (
                project_id,
                brand
            )
        )
        """
    )

    print("✓ ws_project_brands ready")


def create_customer_erp_index(conn) -> None:
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_ws_customers_unique_erp_customer
        ON ws_customers (
            erp_customer_id
        )
        WHERE erp_customer_id IS NOT NULL
          AND TRIM(erp_customer_id) <> ''
        """
    )

    print("✓ ERP customer duplicate protection ready")


def main() -> None:
    print("=" * 72)
    print("Upgrading Workspace project MVP schema")
    print("=" * 72)

    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        add_sales_rep_column(conn)
        create_project_quotes_table(conn)
        create_project_brands_table(conn)
        create_customer_erp_index(conn)

        conn.commit()

    print("=" * 72)
    print("✅ Project MVP schema upgrade completed")
    print("=" * 72)


if __name__ == "__main__":
    main()