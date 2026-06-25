from app.database.reader import read_table


def main():

    df = read_table("raw_customers")

    print("=" * 80)
    print("RAW CUSTOMERS")
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

    print("\n")
    print("=" * 80)
    print("escliente")
    print("=" * 80)

    print(df["escliente"].value_counts(dropna=False))

    print("\nUnique values")
    print(df["escliente"].unique())

    print("\n")
    print("=" * 80)
    print("cliente_credito")
    print("=" * 80)

    print(df["cliente_credito"].value_counts(dropna=False))

    print("\nUnique values")
    print(df["cliente_credito"].unique())

    print("\n")
    print("=" * 80)
    print("Payment Terms")
    print("=" * 80)

    print(df["plazopagocc"].value_counts(dropna=False).head(20))

    print("\n")
    print("=" * 80)
    print("Credit Limit")
    print("=" * 80)

    print(df["cupocreditocc"].describe())

    print("\n")
    print("=" * 80)
    print("Cities")
    print("=" * 80)

    print(df["ciudad"].value_counts().head(20))

    print("\n")
    print("=" * 80)
    print("Sellers")
    print("=" * 80)

    print(df["vendedor"].value_counts())

    print("\n")
    print("=" * 80)
    print("Economic Activity (idciiu)")
    print("=" * 80)

    print(df["idciiu"].value_counts().head(20))


if __name__ == "__main__":
    main()