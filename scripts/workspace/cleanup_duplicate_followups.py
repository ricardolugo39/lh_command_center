from app.database.connection import get_connection


def main() -> None:
    with get_connection() as conn:
        before_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ws_followups
            """
        ).fetchone()[0]

        conn.execute(
            """
            DELETE FROM ws_followups
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM ws_followups
                GROUP BY
                    project_id,
                    due_date,
                    description,
                    status
            )
            """
        )

        conn.commit()

        after_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ws_followups
            """
        ).fetchone()[0]

    print("✅ Duplicate follow-ups cleaned")
    print(f"Rows before:       {before_count}")
    print(f"Rows after:        {after_count}")
    print(f"Duplicates removed: {before_count - after_count}")


if __name__ == "__main__":
    main()