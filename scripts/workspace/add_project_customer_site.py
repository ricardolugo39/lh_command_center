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


def main() -> None:
    with get_connection() as conn:
        if not column_exists(
            conn,
            "ws_projects",
            "customer_site_id",
        ):
            conn.execute(
                """
                ALTER TABLE ws_projects
                ADD COLUMN customer_site_id TEXT
                """
            )
            print("✓ Added ws_projects.customer_site_id")
        else:
            print("✓ ws_projects.customer_site_id already exists")

        if not column_exists(
            conn,
            "ws_projects",
            "sales_rep",
        ):
            conn.execute(
                """
                ALTER TABLE ws_projects
                ADD COLUMN sales_rep TEXT
                """
            )
            print("✓ Added ws_projects.sales_rep")
        else:
            print("✓ ws_projects.sales_rep already exists")

        conn.commit()

    print("✅ Project customer-site migration completed")


if __name__ == "__main__":
    main()