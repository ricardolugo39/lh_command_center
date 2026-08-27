from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.utils.datetime import from_excel


@dataclass(frozen=True)
class InventoryIssue:
    row_number: int | None
    severity: str
    code: str
    message: str
    details: dict[str, Any]


INVENTORY_COLUMNS = (
    ("A", "Código", "idproducto"),
    ("B", "Nombre Producto", "nombreproducto"),
    ("C", "Cód", "idbodega"),
    ("D", "Denominación", "nombre_bodega"),
    ("E", "Cód Unidad", "unidad_medida"),
    ("F", "Unidades", "unidades"),
    ("G", "Promedio", "costo_unitario"),
    ("H", "Total", "valor_total"),
    ("I", "Cód", "idfam1"),
    ("J", "Denominación", "nombre_fam1"),
    ("K", "Cód", "idfam2"),
    ("L", "Denominación", "nombre_fam2"),
    ("M", "Cód", "idfam3"),
    ("N", "Denominación", "nombre_fam3"),
    ("O", "Cód", "marca_codigo"),
    ("P", "Denominación", "marca_nombre"),
    ("Q", "Cód", "grupo_fabricante_codigo"),
    ("R", "Denominación", "grupo_fabricante_nombre"),
    ("S", "Ultimo Costo", "ultimo_costo_informativo"),
    ("T", "Ultima Entrada", "ultima_entrada"),
    ("U", "Reservado", "unidades_reservado"),
    ("V", "Remisionado", "unidades_remisionado"),
    ("W", "Disponible", "unidades_disponible"),
    ("X", "1", "transito_1"),
    ("Y", "2", "transito_2"),
    ("Z", "3", "transito_3"),
    ("AA", "Ubicación", "ubicacion"),
    ("AB", "Código barras", "codigo_barras"),
)

NUMERIC_COLUMNS = (
    "unidades",
    "costo_unitario",
    "valor_total",
    "ultimo_costo_informativo",
    "unidades_reservado",
    "unidades_remisionado",
    "unidades_disponible",
    "transito_1",
    "transito_2",
    "transito_3",
)


def read_inventory_file(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, header=None, dtype=object)
    return pd.read_excel(path, header=None, dtype=object)


def normalize_inventory(
    source: pd.DataFrame,
) -> tuple[pd.DataFrame, list[InventoryIssue], list[tuple[str, str]]]:
    if source.empty or len(source.index) < 2:
        raise ValueError("El archivo de inventario no contiene filas de datos.")
    expected_count = len(INVENTORY_COLUMNS)
    if len(source.columns) < expected_count:
        raise ValueError(
            f"El inventario tiene {len(source.columns)} columnas; "
            f"se esperaban al menos {expected_count}."
        )

    headers = [_text(value) for value in source.iloc[0, :expected_count]]
    mismatches = []
    for index, (letter, expected, _canonical) in enumerate(INVENTORY_COLUMNS):
        if _header(headers[index]) != _header(expected):
            mismatches.append(
                f"{letter}: se esperaba “{expected}” y llegó "
                f"“{headers[index] or '(vacío)'}”"
            )
    if mismatches:
        raise ValueError(
            "La estructura del inventario no coincide con el formato validado: "
            + "; ".join(mismatches)
        )
    trailing = source.iloc[:, expected_count:]
    if not trailing.empty and trailing.notna().any().any():
        raise ValueError(
            "El archivo contiene columnas adicionales después de “Código barras”."
        )

    canonical = [item[2] for item in INVENTORY_COLUMNS]
    data = source.iloc[1:, :expected_count].copy()
    data.columns = canonical
    data = data.dropna(how="all").reset_index(drop=True)
    data["_source_row"] = data.index + 2
    issues: list[InventoryIssue] = []

    for column in NUMERIC_COLUMNS:
        raw = data[column]
        converted = pd.to_numeric(raw, errors="coerce")
        invalid = raw.notna() & converted.isna()
        for index in data.index[invalid]:
            issues.append(InventoryIssue(
                row_number=int(data.at[index, "_source_row"]),
                severity="error",
                code="CANTIDAD_NO_NUMERICA",
                message=(
                    f"La columna “{column}” debe ser numérica "
                    f"(valor recibido: {raw.at[index]})."
                ),
                details={"column": column, "value": str(raw.at[index])},
            ))
        data[column] = converted

    for column in (
        "unidades", "unidades_reservado", "unidades_remisionado",
        "unidades_disponible", "transito_1", "transito_2", "transito_3",
    ):
        data[column] = data[column].fillna(0.0)

    for column in canonical:
        if column not in NUMERIC_COLUMNS and column != "ultima_entrada":
            data[column] = data[column].map(_nullable_text)

    for index, row in data.iterrows():
        row_number = int(row["_source_row"])
        if not row["idproducto"]:
            issues.append(InventoryIssue(
                row_number, "error", "PRODUCTO_VACIO",
                "La fila no tiene código de producto.", {},
            ))
        if not row["idbodega"] or not row["nombre_bodega"]:
            issues.append(InventoryIssue(
                row_number, "error", "BODEGA_NO_RECONOCIDA",
                "La fila debe incluir código y denominación de bodega.",
                {
                    "idbodega": row["idbodega"],
                    "nombre_bodega": row["nombre_bodega"],
                },
            ))
        if (
            pd.notna(row["valor_total"])
            and pd.notna(row["costo_unitario"])
            and abs(
                row["valor_total"] - row["unidades"] * row["costo_unitario"]
            ) > 0.01
        ):
            issues.append(InventoryIssue(
                row_number, "warning", "VALOR_INVENTARIO",
                "Total no coincide con unidades × costo promedio.",
                {},
            ))

    data["ultima_entrada"] = data["ultima_entrada"].map(_date_value)
    data["unidades_transito"] = (
        data["transito_1"] + data["transito_2"] + data["transito_3"]
    )
    duplicated = data.duplicated(["idbodega", "idproducto"], keep=False)
    for index in data.index[duplicated]:
        issues.append(InventoryIssue(
            int(data.at[index, "_source_row"]),
            "error",
            "CLAVE_DUPLICADA",
            "El producto aparece más de una vez para la misma bodega.",
            {
                "idbodega": data.at[index, "idbodega"],
                "idproducto": data.at[index, "idproducto"],
            },
        ))

    output_columns = [
        canonical_name
        for canonical_name in canonical
        if canonical_name != "ultimo_costo_informativo"
    ] + ["unidades_transito"]
    mapping = [
        (f"{letter} · {source_name}", canonical_name)
        for letter, source_name, canonical_name in INVENTORY_COLUMNS
    ]
    return data[output_columns], issues, mapping


def _header(value: str) -> str:
    return (
        value.strip().casefold()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u")
    )


def _text(value: Any) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _nullable_text(value: Any) -> str | None:
    text = _text(value)
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def _date_value(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, (int, float)):
        return from_excel(value).date().isoformat()
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else parsed.date().isoformat()
