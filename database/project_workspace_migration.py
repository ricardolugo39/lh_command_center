from app.database.connection import get_connection


PROJECT_WORKSPACE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS crm_customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    erp_customer_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_crm_customers_erp_customer_id
ON crm_customers(erp_customer_id)
WHERE erp_customer_id IS NOT NULL
  AND erp_customer_id <> '';


CREATE TABLE IF NOT EXISTS crm_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'prospect'
        CHECK (
            status IN (
                'prospect',
                'quoting',
                'waiting_customer',
                'negotiation',
                'won',
                'lost'
            )
        ),
    objective TEXT NOT NULL,
    proposed_solution TEXT,
    current_blocker TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT,

    FOREIGN KEY (customer_id)
        REFERENCES crm_customers(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_crm_projects_customer_id
ON crm_projects(customer_id);

CREATE INDEX IF NOT EXISTS idx_crm_projects_status
ON crm_projects(status);


CREATE TABLE IF NOT EXISTS crm_followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    followup_date TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'completed', 'cancelled')),
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (project_id)
        REFERENCES crm_projects(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crm_followups_project_id
ON crm_followups(project_id);

CREATE INDEX IF NOT EXISTS idx_crm_followups_date_status
ON crm_followups(followup_date, status);


CREATE TABLE IF NOT EXISTS crm_open_loops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'closed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT,

    FOREIGN KEY (project_id)
        REFERENCES crm_projects(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crm_open_loops_project_id
ON crm_open_loops(project_id);

CREATE INDEX IF NOT EXISTS idx_crm_open_loops_status
ON crm_open_loops(status);


CREATE TABLE IF NOT EXISTS crm_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    activity_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (project_id)
        REFERENCES crm_projects(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crm_activities_project_id
ON crm_activities(project_id);

CREATE INDEX IF NOT EXISTS idx_crm_activities_occurred_at
ON crm_activities(occurred_at);


CREATE TABLE IF NOT EXISTS crm_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (project_id)
        REFERENCES crm_projects(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crm_notes_project_id
ON crm_notes(project_id);


CREATE TABLE IF NOT EXISTS crm_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (project_id)
        REFERENCES crm_projects(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crm_files_project_id
ON crm_files(project_id);
"""


def run_project_workspace_migration() -> None:
    with get_connection() as conn:
        conn.executescript(PROJECT_WORKSPACE_SCHEMA)
        conn.commit()