from pathlib import Path

from app.sources.excel_source import ExcelSource


EXCEL_FILE = Path("data/raw/customer_segments.xlsx")


def main():

    df = ExcelSource.read(EXCEL_FILE)

    print("=" * 80)
    print("CUSTOMER SEGMENTS")
    print("=" * 80)

    print(f"Rows: {len(df)}")
    print(f"Columns: {len(df.columns)}")

    print("\nColumn Names")
    print("-" * 80)

    for col in df.columns:
        print(col)

    print("\nPreview")
    print("-" * 80)

    print(df.head())


if __name__ == "__main__":
    main()