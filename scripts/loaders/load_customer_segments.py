from pathlib import Path

from app.sources.excel_source import ExcelSource
from app.database.writer import save_raw_table


EXCEL_FILE = Path("data/raw/customer_segments.xlsx")
TABLE_NAME = "raw_customer_segments"


def main():
    print("Reading customer segments Excel...")

    df = ExcelSource.read(EXCEL_FILE)

    print(f"Rows loaded: {len(df)}")
    print(f"Columns loaded: {len(df.columns)}")

    print(f"Saving RAW table: {TABLE_NAME}")

    save_raw_table(
        df=df,
        table_name=TABLE_NAME,
    )

    print(f"✅ {TABLE_NAME} created")


if __name__ == "__main__":
    main()