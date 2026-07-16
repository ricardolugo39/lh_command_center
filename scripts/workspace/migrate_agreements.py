from app.database.connection import get_connection


AGREEMENT_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ws_agreements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    customer_id INTEGER NOT NULL,

    agreement_number TEXT,
    name TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (
            status IN (
                'draft',
                'active',
                'renewal',
                'expired',
                'closed'
            )
        ),

    agreement_type TEXT,
    supplier TEXT,

    annual_target REAL,
    currency TEXT NOT NULL DEFAULT 'COP',

    start_date TEXT,
    end_date TEXT,
    renewal_date TEXT,

    has_consignment INTEGER NOT NULL DEFAULT 0
        CHECK (has_consignment IN (0, 1)),

    notes TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_id)
        REFERENCES ws_customers(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ws_agreements_customer_id
ON ws_agreements(customer_id);

CREATE INDEX IF NOT EXISTS idx_ws_agreements_status
ON ws_agreements(status);
"""


def migrate() -> None:
    with get_connection() as conn:
        conn.executescript(AGREEMENT_SCHEMA)
        conn.commit()

    print("✓ ws_agreements ready")


if __name__ == "__main__":
    migrate()