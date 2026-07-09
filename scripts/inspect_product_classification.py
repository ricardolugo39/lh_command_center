from app.sources.excel_source import ExcelSource


def main():

    df = ExcelSource.read("data/raw/product_classification.xlsx")

    print("=" * 80)
    print("PRODUCT CLASSIFICATION")
    print("=" * 80)

    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")

    print("\nColumns")
    print("-" * 80)
    print(df.columns.tolist())

    print("\nUnique Families")
    print("-" * 80)
    print(df["Familia"].dropna().unique())

    print("\nLast 30 rows")
    print("-" * 80)
    print(df.tail(30))


if __name__ == "__main__":
    main()