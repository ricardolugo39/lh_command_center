from sqlite3 import Connection

from app.database.connection import get_connection


PROJECTS_TABLE = "ws_projects"


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
    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        row["name"] == column_name
        for row in rows
    )


def add_initiative_id_to_projects(
    conn: Connection,
) -> None:
    if column_exists(
        conn,
        PROJECTS_TABLE,
        "initiative_id",
    ):
        print(
            "✓ ws_projects.initiative_id already exists"
        )
        return

    conn.execute(
        """
        ALTER TABLE ws_projects
        ADD COLUMN initiative_id INTEGER
        """
    )

    print(
        "✓ Added ws_projects.initiative_id"
    )


def create_initiatives_table(
    conn: Connection,
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ws_initiatives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            status TEXT NOT NULL DEFAULT 'planning'
                CHECK (
                    status IN (
                        'planning',
                        'active',
                        'paused',
                        'completed'
                    )
                ),

            objective TEXT NOT NULL,
            description TEXT,
            strategy TEXT,

            partner TEXT,
            owner TEXT NOT NULL,

            start_date TEXT,
            expected_end_date TEXT,

            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            updated_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            closed_at TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_ws_initiatives_status
        ON ws_initiatives(status)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_ws_initiatives_owner
        ON ws_initiatives(owner)
        """
    )

    print("✓ ws_initiatives ready")


def create_initiative_events_table(
    conn: Connection,
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS
        ws_initiative_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            initiative_id INTEGER NOT NULL,

            event_type TEXT NOT NULL
                DEFAULT 'update',

            title TEXT NOT NULL,
            details TEXT,

            occurred_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            created_by TEXT NOT NULL
                DEFAULT 'system',

            FOREIGN KEY (initiative_id)
                REFERENCES ws_initiatives(id)
                ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_ws_initiative_events_initiative
        ON ws_initiative_events(
            initiative_id,
            occurred_at
        )
        """
    )

    print("✓ ws_initiative_events ready")


def create_initiative_learnings_table(
    conn: Connection,
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS
        ws_initiative_learnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            initiative_id INTEGER NOT NULL,

            category TEXT NOT NULL
                CHECK (
                    category IN (
                        'worked',
                        'did_not_work',
                        'insight',
                        'objection',
                        'recommendation'
                    )
                ),

            title TEXT NOT NULL,
            details TEXT NOT NULL,

            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            created_by TEXT NOT NULL
                DEFAULT 'system',

            FOREIGN KEY (initiative_id)
                REFERENCES ws_initiatives(id)
                ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_ws_initiative_learnings_initiative
        ON ws_initiative_learnings(
            initiative_id,
            category
        )
        """
    )

    print("✓ ws_initiative_learnings ready")


def create_initiative_decisions_table(
    conn: Connection,
) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS
        ws_initiative_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            initiative_id INTEGER NOT NULL,

            decision TEXT NOT NULL,
            reason TEXT,

            decided_by TEXT NOT NULL,
            decision_date TEXT NOT NULL,

            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (initiative_id)
                REFERENCES ws_initiatives(id)
                ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_ws_initiative_decisions_initiative
        ON ws_initiative_decisions(
            initiative_id,
            decision_date
        )
        """
    )

    print("✓ ws_initiative_decisions ready")


def create_project_initiative_index(
    conn: Connection,
) -> None:
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_ws_projects_initiative_id
        ON ws_projects(initiative_id)
        """
    )

    print(
        "✓ idx_ws_projects_initiative_id ready"
    )


def run_migration() -> None:
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        if not table_exists(
            conn,
            PROJECTS_TABLE,
        ):
            raise RuntimeError(
                "Required table does not exist: "
                f"{PROJECTS_TABLE}"
            )

        create_initiatives_table(conn)

        add_initiative_id_to_projects(conn)
        create_project_initiative_index(conn)

        create_initiative_events_table(conn)
        create_initiative_learnings_table(conn)
        create_initiative_decisions_table(conn)

        conn.commit()


def main() -> None:
    print("=" * 72)
    print("Initiative Module Migration")
    print("=" * 72)

    run_migration()

    print("=" * 72)
    print("✅ Initiative module migration completed")
    print("=" * 72)


if __name__ == "__main__":
    main()