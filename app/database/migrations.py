from app.database.connection import get_connection
from app.workspace.schema import WORKSPACE_SCHEMA


def upgrade() -> None:
    with get_connection() as conn:
        conn.executescript(WORKSPACE_SCHEMA)
        conn.commit()


def downgrade() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            DROP TABLE IF EXISTS ws_activities;
            DROP TABLE IF EXISTS ws_followups;
            DROP TABLE IF EXISTS ws_projects;
            DROP TABLE IF EXISTS ws_customers;
            """
        )
        conn.commit()