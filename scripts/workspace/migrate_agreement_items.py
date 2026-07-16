from app.database.connection import get_connection


AGREEMENT_ITEMS_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ws_agreement_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    agreement_id INTEGER NOT NULL,

    part_number TEXT NOT NULL,
    skf_reference TEXT NOT NULL,

    list_price_usd REAL,
    agreement_price_usd REAL,
    suggested_price_usd REAL,

    product_line TEXT,
    spc TEXT,

    source_file_name TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (agreement_id)
        REFERENCES ws_agreements(id)
        ON DELETE CASCADE,

    UNIQUE (
        agreement_id,
        part_number,
        skf_reference
    )
);

CREATE INDEX IF NOT EXISTS
idx_ws_agreement_items_agreement_id
ON ws_agreement_items(agreement_id);

CREATE INDEX IF NOT EXISTS
idx_ws_agreement_items_part_number
ON ws_agreement_items(part_number);

CREATE INDEX IF NOT EXISTS
idx_ws_agreement_items_reference
ON ws_agreement_items(skf_reference);
"""


def migrate() -> None:
    with get_connection() as conn:
        conn.executescript(
            AGREEMENT_ITEMS_SCHEMA
        )
        conn.commit()

    print("✓ ws_agreement_items ready")


if __name__ == "__main__":
    migrate()