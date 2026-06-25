from pathlib import Path

from app.sources.excel_source import ExcelSource


EXCEL_FILE = Path("data/raw/product_classification.xlsx")


def main():

    df = ExcelSource.read(EXCEL_FILE)

    print("=" * 60)
    print("Rows:", len(df))
    print("Columns:", len(df.columns))
    print("=" * 60)

    print(df.head())


if __name__ == "__main__":
    main()