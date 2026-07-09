from app.database.reader import read_table


def main():

    df = read_table("raw_sales")

    print("=" * 80)
    print("RAW SALES")
    print("=" * 80)

    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")

    print("\nColumns")
    print("-" * 80)

    for col in df.columns:
        print(col)

    print("\nPreview")
    print("-" * 80)

    print(df.head())


if __name__ == "__main__":
    main()