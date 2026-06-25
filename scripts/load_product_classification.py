from pathlib import Path

from app.sources.excel_source import ExcelSource
from app.database.writer import save_raw_table


EXCEL_FILE = Path("data/raw/product_classification.xlsx")


def main():

    print("Reading Excel...")

    df = ExcelSource.read(EXCEL_FILE)

    print(f"Loaded {len(df)} rows")

    print("Saving RAW table...")

    save_raw_table(
        df=df,
        table_name="raw_product_classification",
    )

    print("✅ RAW table created")


if __name__ == "__main__":
    main()