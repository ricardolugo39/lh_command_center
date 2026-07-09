from pathlib import Path
import sqlite3
import sys
import pandas as pd

sys.path.append(str(Path.cwd()))

from app.importers.access_importer import get_table_data


ACCESS_FILE = Path("/Users/ricardolugo/Library/CloudStorage/OneDrive-Personal/LH/Reports/sales_lh.accdb")
DB_PATH = Path("database/commercial.db")

TABLES = {
    "sales": "raw_sales",
    "customers": "raw_customers",
}

def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize raw ERP data before writing to SQLite.
    """

    df = df.copy()

    # Normalize column names
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
    )

    # Normalize sales date
    if "fecha" in df.columns:

        df["fecha"] = pd.to_datetime(
            df["fecha"],
            format="%m/%d/%y %H:%M:%S",
            errors="coerce",
        )

        df["fecha"] = df["fecha"].dt.strftime("%Y-%m-%d")

    return df

def migrate_table(access_table: str, sqlite_table: str, conn: sqlite3.Connection):
    print(f"\nMigrating {access_table} → {sqlite_table}")

    df = get_table_data(ACCESS_FILE, access_table)

    df = normalize_dataframe(df)

    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")

    df.to_sql(
        sqlite_table,
        conn,
        if_exists="replace",
        index=False,
    )

    print(f"Done: {sqlite_table}")


def main():
    if not ACCESS_FILE.exists():
        raise FileNotFoundError(f"Access file not found: {ACCESS_FILE}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    for access_table, sqlite_table in TABLES.items():
        migrate_table(access_table, sqlite_table, conn)

    conn.close()

    print("\nMigration completed.")
    print(f"SQLite database: {DB_PATH.resolve()}")


if __name__ == "__main__":
    main()