"""Nivel inicial simple de consignación para SERMOTOR.

Reutiliza literalmente el parser y el universo del análisis original. Lee la BD
en modo read-only y genera tres tablas más un resumen.
"""

from __future__ import annotations

import math
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from .analyze_sermotor_consignacion import (
        LISTA_CLIENTE_CSV,
        add_parser_columns,
        ceil_even,
        load_sales,
        normalize_designation,
        recent_costs,
    )
except ImportError:  # Permite ejecutar el archivo directamente.
    from analyze_sermotor_consignacion import (
        LISTA_CLIENTE_CSV,
        add_parser_columns,
        ceil_even,
        load_sales,
        normalize_designation,
        recent_costs,
    )


MESES_COBERTURA = 2.5
UMBRAL_PAR = 100_000
VENTANA_MESES = 12
CONCENTRACION_SELLO = 0.80

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "sermotor_nivel_inicial"


def skf_dispatch_reference(key: str, eligible_all: pd.DataFrame) -> str:
    """Obtiene la referencia SKF vendida más reciente o genera su nomenclatura."""
    size, seal, play = key.split(" | ")
    matches = eligible_all[
        eligible_all["parser_llave_canonica"].eq(key)
        & eligible_all["sufijo"].eq("SKF")
    ].sort_values(["fecha", "sales_line_key"], ascending=False)
    if not matches.empty:
        reference = str(matches.iloc[0]["prefijo_1"])
        # Se conserva la nomenclatura real; GJN no aplica a algunas referencias,
        # por ejemplo 608, pero nunca se inventa si no existe en el histórico.
        return reference

    if seal == "METAL":
        seal_code = "2Z"
    elif seal == "CAUCHO":
        number = int(size)
        seal_code = "2RSH" if size == "608" or number % 100 <= 5 else "2RS1"
    else:
        return f"{size}/C3" if play == "C3" else size
    play_code = "/C3GJN" if play == "C3" else "/GJN"
    return f"{size}-{seal_code}{play_code}"


def load_client_list() -> pd.DataFrame:
    data = pd.read_csv(StringIO(LISTA_CLIENTE_CSV))
    parsed = pd.DataFrame(
        data["referencia"].map(normalize_designation).tolist(), index=data.index
    ).add_prefix("parser_")
    data = pd.concat([data, parsed], axis=1)
    if not data["parser_ok"].all():
        failed = data.loc[~data["parser_ok"], ["referencia", "parser_error"]]
        raise ValueError(f"Anexo no clasificable:\n{failed.to_string(index=False)}")
    return (
        data.groupby("parser_llave_canonica")
        .agg(
            unidades_cliente=("unidades", "sum"),
            referencias_cliente=("referencia", lambda values: "|".join(values)),
        )
        .reset_index()
        .rename(columns={"parser_llave_canonica": "llave_canonica"})
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sales = add_parser_columns(load_sales())
    max_date = sales["fecha"].max().normalize()
    start_date = max_date - pd.DateOffset(months=VENTANA_MESES) + pd.Timedelta(days=1)

    rigid = sales["nombreproducto"].fillna("").str.upper().eq(
        "RODAMIENTO RIGIDO DE BOLAS"
    )
    eligible_all = sales[sales["parser_ok"] & rigid].copy()
    window = eligible_all[eligible_all["fecha"].between(start_date, max_date)].copy()

    consumption = (
        window.groupby(
            [
                "parser_llave_canonica",
                "parser_tamano",
                "parser_sello",
                "parser_juego",
            ],
            dropna=False,
        )["cantidad"]
        .sum()
        .reset_index(name="consumo_12m")
        .rename(
            columns={
                "parser_llave_canonica": "llave_canonica",
                "parser_tamano": "tamano",
                "parser_sello": "sello",
                "parser_juego": "juego",
            }
        )
    )
    consumption = consumption[consumption["consumo_12m"] > 0].copy()

    # La regla 80/20 se evalúa sobre las dos variantes selladas intercambiables.
    sealed = consumption[consumption["sello"].isin(["METAL", "CAUCHO"])].copy()
    seal_distribution = (
        sealed.groupby(["tamano", "sello"])["consumo_12m"]
        .sum()
        .reset_index(name="consumo_sello")
    )
    seal_distribution["consumo_tamano"] = seal_distribution.groupby("tamano")[
        "consumo_sello"
    ].transform("sum")
    seal_distribution["participacion_sello"] = (
        seal_distribution["consumo_sello"]
        / seal_distribution["consumo_tamano"]
    )
    sealed = sealed.merge(seal_distribution, on=["tamano", "sello"], how="left")
    dominant = (
        sealed.groupby("tamano")["participacion_sello"].max()
        .ge(CONCENTRACION_SELLO)
        .rename("hay_sello_dominante")
    )
    sealed = sealed.merge(dominant, on="tamano", how="left")
    sealed["seleccionada_por_distribucion"] = (
        ~sealed["hay_sello_dominante"]
        | sealed["participacion_sello"].ge(CONCENTRACION_SELLO)
    )

    open_rows = consumption[consumption["sello"].eq("ABIERTO")].copy()
    open_rows["consumo_tamano"] = open_rows["consumo_12m"]
    open_rows["participacion_sello"] = 1.0
    open_rows["hay_sello_dominante"] = False
    open_rows["seleccionada_por_distribucion"] = True
    candidates = pd.concat([sealed, open_rows], ignore_index=True)

    candidates["consumo_mensual_promedio"] = candidates["consumo_12m"] / 12
    candidates["nivel_crudo"] = (
        candidates["consumo_mensual_promedio"] * MESES_COBERTURA
    )
    candidates = candidates.merge(
        recent_costs(eligible_all), on="llave_canonica", how="left"
    )
    missing_cost = candidates[candidates["costo_unitario_reciente"].isna()]
    if not missing_cost.empty:
        raise ValueError(
            "No hay costo reciente para:\n"
            + missing_cost[["llave_canonica", "consumo_12m"]].to_string(index=False)
        )

    candidates["costo_par"] = 2 * candidates["costo_unitario_reciente"]
    candidates["motivo_no_entra"] = ""
    candidates.loc[
        ~candidates["seleccionada_por_distribucion"], "motivo_no_entra"
    ] = "ROTACION_BAJA"
    candidates.loc[
        candidates["nivel_crudo"].lt(1), "motivo_no_entra"
    ] = "ROTACION_BAJA"
    mid = candidates["nivel_crudo"].ge(1) & candidates["nivel_crudo"].lt(2)
    candidates.loc[
        mid & candidates["costo_par"].ge(UMBRAL_PAR), "motivo_no_entra"
    ] = "COSTO_ALTO"
    candidates["entra"] = candidates["motivo_no_entra"].eq("")
    candidates["nivel_inicial"] = 0
    candidates.loc[candidates["entra"], "nivel_inicial"] = candidates.loc[
        candidates["entra"], "nivel_crudo"
    ].map(ceil_even)
    candidates["meses_cobertura_reales"] = np.where(
        candidates["consumo_mensual_promedio"] > 0,
        candidates["nivel_inicial"] / candidates["consumo_mensual_promedio"],
        np.nan,
    )
    candidates["referencia_skf_sugerida"] = candidates["llave_canonica"].map(
        lambda key: skf_dispatch_reference(key, eligible_all)
    )

    client = load_client_list()
    candidates = candidates.merge(client, on="llave_canonica", how="left")
    candidates["estaba_lista_cliente"] = np.where(
        candidates["unidades_cliente"].notna(), "Sí", "No"
    )
    candidates["unidades_cliente"] = candidates["unidades_cliente"].fillna(0)
    candidates["diferencia_vs_cliente"] = (
        candidates["nivel_inicial"] - candidates["unidades_cliente"]
    )
    candidates["valor_costo"] = (
        candidates["nivel_inicial"] * candidates["costo_unitario_reciente"]
    )

    table_a = candidates[candidates["entra"]].copy().sort_values(
        "valor_costo", ascending=False
    )
    table_a[
        [
            "llave_canonica",
            "referencia_skf_sugerida",
            "consumo_12m",
            "consumo_mensual_promedio",
            "nivel_inicial",
            "meses_cobertura_reales",
            "costo_unitario_reciente",
            "valor_costo",
            "estaba_lista_cliente",
            "unidades_cliente",
            "diferencia_vs_cliente",
            "participacion_sello",
        ]
    ].to_csv(OUTPUT_DIR / "tabla_a_lista_arranque.csv", index=False)

    table_b = candidates[~candidates["entra"]].copy().sort_values(
        ["motivo_no_entra", "consumo_12m"], ascending=[True, False]
    )
    table_b[
        [
            "llave_canonica",
            "referencia_skf_sugerida",
            "consumo_12m",
            "nivel_crudo",
            "costo_unitario_reciente",
            "costo_par",
            "participacion_sello",
            "motivo_no_entra",
        ]
    ].to_csv(OUTPUT_DIR / "tabla_b_no_entran.csv", index=False)

    qualified_keys = set(table_a["llave_canonica"])
    table_c = client[~client["llave_canonica"].isin(qualified_keys)].copy()
    table_c = table_c.merge(
        candidates[
            [
                "llave_canonica",
                "consumo_12m",
                "nivel_crudo",
                "costo_par",
                "motivo_no_entra",
            ]
        ],
        on="llave_canonica",
        how="left",
    )
    table_c["consumo_12m"] = table_c["consumo_12m"].fillna(0)
    table_c["nivel_crudo"] = table_c["nivel_crudo"].fillna(0)
    table_c["motivo_no_entra"] = table_c["motivo_no_entra"].fillna(
        "ROTACION_BAJA"
    )
    table_c.sort_values(
        ["motivo_no_entra", "unidades_cliente"], ascending=[True, False]
    ).to_csv(OUTPUT_DIR / "tabla_c_cliente_sin_respaldo.csv", index=False)

    client_capital = (
        client.merge(recent_costs(eligible_all), on="llave_canonica", how="left")
    )
    client_capital["valor"] = (
        client_capital["unidades_cliente"]
        * client_capital["costo_unitario_reciente"]
    )
    summary = pd.DataFrame(
        [
            {
                "fecha_maxima": max_date.date().isoformat(),
                "inicio_ventana": start_date.date().isoformat(),
                "meses_cobertura_parametro": MESES_COBERTURA,
                "umbral_par": UMBRAL_PAR,
                "referencias_arranque": len(table_a),
                "unidades_arranque": int(table_a["nivel_inicial"].sum()),
                "valor_arranque": table_a["valor_costo"].sum(),
                "referencias_cliente": len(client),
                "unidades_cliente": int(client["unidades_cliente"].sum()),
                "valor_cliente_recalculado": client_capital["valor"].sum(),
                "valor_cliente_referencia_solicitud": 9_096_247,
                "referencias_cliente_sin_respaldo": len(table_c),
                "referencias_no_entran_total": len(table_b),
            }
        ]
    )
    summary.to_csv(OUTPUT_DIR / "resumen.csv", index=False)

    print(f"Ventana: {start_date.date()} a {max_date.date()}")
    print(f"Salidas: {OUTPUT_DIR}")
    print(summary.to_string(index=False))
    print("\nMotivos de no entrada:")
    print(table_b["motivo_no_entra"].value_counts().to_string())


if __name__ == "__main__":
    main()
