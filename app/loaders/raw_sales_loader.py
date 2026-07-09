from pathlib import Path
import hashlib

import pandas as pd

from app.database.reader import read_table, table_exists
from app.database.writer import save_dataframe


REQUIRED_COLUMNS = {
    "nit",
    "razonsocial",
    "prefijo",
    "numero",
    "fecha",
    "idproducto",
    "nombreproducto",
    "cantidad",
    "idfam1",
    "idfam2",
    "valorbruto",
    "costo",
}


def read_file(file_path: str | Path) -> pd.DataFrame:
    file_path = Path(file_path)

    if file_path.suffix.lower() in [".xlsx", ".xls"]:
        return pd.read_excel(file_path)

    if file_path.suffix.lower() == ".csv":
        return pd.read_csv(file_path)

    raise ValueError(f"Unsupported file type: {file_path.suffix}")


def normalize_raw_sales(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df.columns = df.columns.str.strip().str.lower()

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["fecha"] = pd.to_datetime(
        df["fecha"],
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")

    numeric_cols = [
        "numero",
        "cantidad",
        "precio",
        "preciousd",
        "idfam1",
        "idfam2",
        "idbodega",
        "neto",
        "valorbruto",
        "descuento",
        "vdescuento",
        "costo",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["sales_line_key"] = df.apply(build_sales_line_key, axis=1)

    return df


def build_sales_line_key(row) -> str:
    key = "|".join([
        str(row.get("prefijo", "")).strip(),
        str(row.get("numero", "")).strip(),
        str(row.get("fecha", "")).strip(),
        str(row.get("idproducto", "")).strip(),
        str(row.get("cantidad", "")).strip(),
        str(row.get("valorbruto", "")).strip(),
    ])

    return hashlib.md5(key.encode("utf-8")).hexdigest()


def load_raw_sales(file_path: str | Path) -> dict:
    new_df = read_file(file_path)
    new_df = normalize_raw_sales(new_df)

    before_rows = 0

    if table_exists("raw_sales"):
        current_df = read_table("raw_sales")

        if "sales_line_key" not in current_df.columns:
            current_df = normalize_raw_sales(current_df)

        before_rows = len(current_df)

        combined = pd.concat(
            [current_df, new_df],
            ignore_index=True,
        )

        before_dedup = len(combined)

        combined = combined.drop_duplicates(
            subset=["sales_line_key"],
            keep="last",
        )

        duplicates_removed = before_dedup - len(combined)

    else:
        combined = new_df
        duplicates_removed = 0

    save_dataframe(
        df=combined,
        table_name="raw_sales",
        if_exists="replace",
    )

    return {
        "before_rows": before_rows,
        "imported_rows": len(new_df),
        "after_rows": len(combined),
        "duplicates_removed": duplicates_removed,
        "min_date": combined["fecha"].min(),
        "max_date": combined["fecha"].max(),
    }