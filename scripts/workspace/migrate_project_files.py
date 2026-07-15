from app.database.connection import get_connection


def migrate():

    sql = """
    CREATE TABLE IF NOT EXISTS ws_project_files (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        project_id INTEGER NOT NULL,

        category TEXT NOT NULL DEFAULT 'other',

        original_name TEXT NOT NULL,

        stored_name TEXT NOT NULL,

        mime_type TEXT,

        file_size INTEGER,

        uploaded_by TEXT,

        created_at TEXT DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(project_id)
            REFERENCES ws_projects(id)
            ON DELETE CASCADE
    );
    """

    with get_connection() as conn:
        conn.execute(sql)
        conn.commit()

    print("✓ ws_project_files created")


if __name__ == "__main__":
    migrate()