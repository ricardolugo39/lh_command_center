"""Reporte mensual de seguimiento de la consignación SERMOTOR.

Entrada mínima:
    referencia,unidades_en_bodega,fecha_conteo

El CSV puede contener varios conteos por referencia. Opcionalmente acepta una
columna `reposiciones`; si no existe se asume cero y esto se declara en la salida.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from .analyze_sermotor_consignacion import ceil_even, normalize_designation
except ImportError:  # Permite ejecutar el archivo directamente.
    from analyze_sermotor_consignacion import ceil_even, normalize_designation


MESES_COBERTURA = 2.5
CONTEOS_PARA_PROMEDIO = 3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEVELS = (
    PROJECT_ROOT
    / "outputs"
    / "sermotor_nivel_inicial"
    / "tabla_a_lista_arranque.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "outputs"
    / "sermotor_nivel_inicial"
    / "reporte_mensual.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("conteos_csv", type=Path)
    parser.add_argument("--niveles", type=Path, default=DEFAULT_LEVELS)
    parser.add_argument("--salida", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    counts = pd.read_csv(args.conteos_csv)
    required = {"referencia", "unidades_en_bodega", "fecha_conteo"}
    missing = required - set(counts.columns)
    if missing:
        raise ValueError(f"Faltan columnas obligatorias: {sorted(missing)}")
    if "reposiciones" not in counts:
        counts["reposiciones"] = 0
        replenishment_note = "ASUMIDAS_CERO"
    else:
        replenishment_note = "INFORMADAS_EN_ARCHIVO"

    parsed = pd.DataFrame(
        counts["referencia"].map(normalize_designation).tolist(), index=counts.index
    ).add_prefix("parser_")
    counts = pd.concat([counts, parsed], axis=1)
    if not counts["parser_ok"].all():
        failed = counts.loc[
            ~counts["parser_ok"], ["referencia", "parser_error"]
        ]
        raise ValueError(f"Referencias no clasificables:\n{failed.to_string(index=False)}")
    counts["fecha_conteo"] = pd.to_datetime(counts["fecha_conteo"], errors="raise")
    for column in ["unidades_en_bodega", "reposiciones"]:
        counts[column] = pd.to_numeric(counts[column], errors="raise")
        if counts[column].lt(0).any():
            raise ValueError(f"{column} no puede contener valores negativos")

    levels = pd.read_csv(args.niveles)
    levels = levels[
        ["llave_canonica", "referencia_skf_sugerida", "nivel_inicial"]
    ].rename(columns={"nivel_inicial": "nivel_actual_acordado"})
    counts = counts.merge(
        levels,
        left_on="parser_llave_canonica",
        right_on="llave_canonica",
        how="left",
    )
    missing_level = counts[counts["nivel_actual_acordado"].isna()]
    if not missing_level.empty:
        raise ValueError(
            "Referencias sin nivel acordado:\n"
            + missing_level[["referencia", "parser_llave_canonica"]].to_string(
                index=False
            )
        )

    counts = counts.sort_values(["llave_canonica", "fecha_conteo"])
    # Después de cada revisión se repone hasta el nivel acordado; por ello el
    # inventario inicial del periodo es el nivel vigente.
    counts["consumo_periodo"] = (
        counts["nivel_actual_acordado"]
        - counts["unidades_en_bodega"]
        + counts["reposiciones"]
    )
    if counts["consumo_periodo"].lt(0).any():
        bad = counts[counts["consumo_periodo"] < 0]
        raise ValueError(
            "Consumo negativo: revise conteo/reposiciones:\n"
            + bad[["referencia", "fecha_conteo", "consumo_periodo"]].to_string(
                index=False
            )
        )

    grouped = counts.groupby("llave_canonica", group_keys=False)
    counts["consumo_ultimos_3_conteos"] = grouped["consumo_periodo"].transform(
        lambda values: values.rolling(CONTEOS_PARA_PROMEDIO, min_periods=1).sum()
    )
    counts["conteos_acumulados"] = grouped.cumcount() + 1
    counts["consumo_mensual_estimado"] = (
        counts["consumo_ultimos_3_conteos"]
        / counts["conteos_acumulados"].clip(upper=CONTEOS_PARA_PROMEDIO)
    )
    counts["meses_cobertura_nivel_actual"] = np.where(
        counts["consumo_mensual_estimado"] > 0,
        counts["nivel_actual_acordado"] / counts["consumo_mensual_estimado"],
        np.nan,
    )
    counts["nivel_recalculado"] = (
        counts["consumo_mensual_estimado"] * MESES_COBERTURA
    ).map(ceil_even)

    def adjustment(row: pd.Series) -> str:
        if (
            row["conteos_acumulados"] >= CONTEOS_PARA_PROMEDIO
            and row["consumo_ultimos_3_conteos"] == 0
        ):
            return "RETIRAR"
        if row["nivel_recalculado"] > row["nivel_actual_acordado"]:
            return "SUBIR"
        if row["nivel_recalculado"] < row["nivel_actual_acordado"]:
            return "BAJAR"
        return "MANTENER"

    counts["ajuste_sugerido"] = counts.apply(adjustment, axis=1)
    latest = counts.groupby("llave_canonica", as_index=False).tail(1).copy()
    latest["tratamiento_reposiciones"] = replenishment_note
    output_columns = [
        "referencia",
        "referencia_skf_sugerida",
        "nivel_actual_acordado",
        "unidades_en_bodega",
        "reposiciones",
        "consumo_periodo",
        "consumo_ultimos_3_conteos",
        "meses_cobertura_nivel_actual",
        "nivel_recalculado",
        "ajuste_sugerido",
        "fecha_conteo",
        "tratamiento_reposiciones",
    ]
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    latest[output_columns].to_csv(args.salida, index=False)
    print(f"Reporte generado: {args.salida}")
    print(f"Reposiciones: {replenishment_note}")


if __name__ == "__main__":
    main()
