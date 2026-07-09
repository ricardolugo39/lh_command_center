from pathlib import Path

import pandas as pd


INBOX_DIR = Path("data/inbox/sales")
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


def read_file(file_path: Path) -> pd.DataFrame:
    if file_path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)

    if file_path.suffix.lower() == ".csv":
        return pd.read_csv(file_path)

    raise ValueError(f"Unsupported file type: {file_path.suffix}")


def main():
    files = [
        file
        for file in INBOX_DIR.iterdir()
        if file.is_file() and file.suffix.lower() in ALLOWED_EXTENSIONS
    ]

    if not files:
        print("No sales files found in data/inbox/sales")
        return

    for file_path in files:
        print("=" * 80)
        print(f"FILE: {file_path}")
        print("=" * 80)

        df = read_file(file_path)

        print(f"Rows: {len(df):,}")
        print(f"Columns: {len(df.columns)}")

        print("\nColumns")
        print("-" * 80)
        for col in df.columns:
            print(col)

        print("\nPreview")
        print("-" * 80)
        print(df.head())

        if "fecha" in [c.lower() for c in df.columns]:
            fecha_col = [c for c in df.columns if c.lower() == "fecha"][0]

            print("\nFecha sample")
            print("-" * 80)
            print(df[fecha_col].head(10))

            parsed = pd.to_datetime(df[fecha_col], errors="coerce")

            print("\nParsed date check")
            print("-" * 80)
            print("Null parsed:", parsed.isna().sum())
            print("Min date:", parsed.min())
            print("Max date:", parsed.max())


if __name__ == "__main__":
    main()