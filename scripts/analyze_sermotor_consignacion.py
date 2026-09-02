"""Dimensionamiento reproducible de la consignación de rodamientos de SERMOTOR.

Lee database/commercial.db en modo read-only y escribe CSV en
outputs/sermotor_consignacion/. No modifica la base de datos.
"""

from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


# Parámetros de negocio
CICLO_REPOSICION_DIAS = 14
LEAD_TIME_DIAS = 3
NIVEL_SERVICIO = 0.95
Z_NIVEL_SERVICIO = 1.65
VENTANA_MESES = 12
NIT_CLIENTE = "900611187"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "database" / "commercial.db"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "sermotor_consignacion"

LISTA_CLIENTE_CSV = """referencia,unidades
6002-2Z/C3GJN,2
6004-2RSH/C3GJN,2
6004-2Z/C3GJN,2
608-2RSH/C3,2
608-2Z/C3,2
6201-2RSH/C3GJN,2
6201-2Z/C3GJN,2
6201-2Z/C3GJN,2
6202-2RSH/C3GJN,4
6202-2Z/C3GJN,4
6203-2RSH/C3GJN,8
6203-2Z/C3GJN,4
6204-2RSH/C3GJN,8
6204-2Z/C3GJN,4
6205-2RSH/C3GJN,8
6205-2Z/C3GJN,8
6206-2RS1/C3GJN,8
6206-2RS1/C3GJN,2
6206-2Z/C3GJN,8
6207-2RS1/C3GJN,2
6207-2Z/C3GJN,2
6208-2RS1/C3GJN,2
6208-2Z/C3GJN,2
6209-2RS1/C3GJN,2
6209-2Z/C3GJN,2
6210-2RS1/C3GJN,2
6210-2Z/C3GJN,2
6211-2RS1/C3GJN,2
6211-2Z/C3GJN,1
6212-2RS1/C3GJN,2
6212-2Z/C3GJN,2
6213-2RS1/C3GJN,2
6213-2Z/C3GJN,1
6300-2Z/C3GJN,2
6303-2RSH/C3GJN,2
6303-2Z/C3GJN,2
6304-2RSH/C3GJN,2
6304-2Z/C3GJN,2
6305-2RS1/C3GJN,2
6305-2Z/C3GJN,2
6306-2RS1/C3GJN,4
6306-2Z/C3GJN,4
6307-2RS1/C3GJN,2
6307-2Z/C3GJN,2
6308-2RS1/C3GJN,4
6308-2Z/C3GJN,2
6309-2RS1/C3GJN,4
6309-2Z/C3GJN,2
6310-2RS1/C3GJN,2
6310-2Z/C3GJN,2
6311-2RS1/C3GJN,2
6311-2Z/C3GJN,2
6312-2RS1/C3GJN,2
6312-2Z/C3GJN,2
6313-2RS1/C3GJN,2
6313-2Z/C3GJN,2
6314-2RS1/C3GJN,1
6314-2Z/C3GJN,1
6316-2RS1/C3GJN,1
6317-2RS1/C3GJN,1
6318-2Z/C3GJN,1
"""

SEAL_PATTERNS = (
    ("CAUCHO", r"(?<![A-Z0-9])C-2HRS(?![A-Z0-9])"),
    ("CAUCHO", r"(?<![A-Z0-9])2RS1(?![A-Z0-9])"),
    ("CAUCHO", r"(?<![A-Z0-9])2RSH(?![A-Z0-9])"),
    ("CAUCHO", r"(?<![A-Z0-9])2RSR(?![A-Z0-9])"),
    ("CAUCHO", r"(?<![A-Z0-9])DDU(?![A-Z0-9])"),
    ("CAUCHO", r"(?<![A-Z0-9])LLU(?![A-Z0-9])"),
    ("CAUCHO", r"(?<![A-Z0-9])2RS(?![A-Z0-9])"),
    ("METAL", r"(?<![A-Z0-9])2ZR(?![A-Z0-9])"),
    ("METAL", r"(?<![A-Z0-9])2Z(?![A-Z0-9])"),
    ("METAL", r"(?<![A-Z0-9])ZZ(?![A-Z0-9])"),
)


def normalize_designation(value: object) -> dict[str, object]:
    """Convierte una designación en tamaño|sello|juego, sin ocultar fallos."""
    raw = "" if pd.isna(value) else str(value).strip().upper()
    compact = re.sub(r"\s+", "", raw)
    size_match = re.match(r"^(608|60\d{2}|62\d{2}|63\d{2})(?=$|[-/ ])", raw)
    if not size_match:
        # Algunas referencias no traen separador después del tamaño.
        size_match = re.match(r"^(608|60\d{2}|62\d{2}|63\d{2})", compact)
    if not size_match:
        return {"ok": False, "error": "TAMAÑO_NO_CLASIFICADO", "raw": raw}

    size = size_match.group(1)
    if re.search(r"(?<![A-Z])NR(?![A-Z])", raw) or re.search(r"NR$", compact):
        return {"ok": False, "error": "ANILLO_NR_EXCLUIDO", "raw": raw, "tamano": size}

    seals = {
        concept
        for concept, pattern in SEAL_PATTERNS
        if re.search(pattern, raw.replace("/", "-"))
    }
    if len(seals) > 1:
        return {"ok": False, "error": "SELLO_AMBIGUO", "raw": raw, "tamano": size}
    seal = next(iter(seals), "ABIERTO")

    # En SKF la grasa puede venir pegada al juego: /C3GJN.
    play = (
        "C3"
        if re.search(
            r"(?<![A-Z0-9])C3(?=$|[-/ ]|GJN|L038|MT33|WT|LHT23)",
            raw.replace("/", "-"),
        )
        else "NORMAL"
    )
    grease_tokens = re.findall(r"(?:GJN|L038|MT33|WT|LHT23)", raw)
    grease = "|".join(dict.fromkeys(grease_tokens))
    return {
        "ok": True,
        "error": "",
        "raw": raw,
        "tamano": size,
        "sello": seal,
        "juego": play,
        "grasa": grease,
        "llave_canonica": f"{size} | {seal} | {play}",
    }


def ceil_even(value: float) -> int:
    if not np.isfinite(value) or value <= 0:
        return 0
    rounded = math.ceil(value)
    return rounded if rounded < 2 or rounded % 2 == 0 else rounded + 1


def classify_demand(adi: float, cv2: float) -> str:
    if adi <= 1.32 and cv2 <= 0.49:
        return "SMOOTH"
    if adi <= 1.32 and cv2 > 0.49:
        return "ERRATICO"
    if adi > 1.32 and cv2 <= 0.49:
        return "INTERMITENTE"
    return "LUMPY"


def load_sales() -> pd.DataFrame:
    uri = f"file:{DB_PATH}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        frame = pd.read_sql_query(
            """
            SELECT nit, razonsocial, prefijo, numero, fecha, ordencompra,
                   idproducto, nombreproducto, prefijo_1, sufijo, cantidad,
                   idunidad, precio, neto, costo, sales_line_key
            FROM raw_sales
            WHERE nit = ?
            """,
            connection,
            params=(NIT_CLIENTE,),
        )
    frame["fecha"] = pd.to_datetime(frame["fecha"], errors="raise")
    return frame


def add_parser_columns(frame: pd.DataFrame) -> pd.DataFrame:
    parsed = pd.DataFrame(frame["prefijo_1"].map(normalize_designation).tolist(), index=frame.index)
    return pd.concat([frame, parsed.add_prefix("parser_")], axis=1)


def demand_metrics(
    window: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    horizon = CICLO_REPOSICION_DIAS + LEAD_TIME_DIAS
    records: list[dict[str, object]] = []
    for key, group in window.groupby("parser_llave_canonica"):
        daily = group.groupby("fecha")["cantidad"].sum().reindex(days, fill_value=0.0)
        bucket_number = ((daily.index - start).days // CICLO_REPOSICION_DIAS).astype(int)
        buckets = daily.groupby(bucket_number).sum()
        positive_buckets = buckets[buckets > 0]
        adi = len(buckets) / len(positive_buckets) if len(positive_buckets) else math.inf
        if len(positive_buckets) > 1 and positive_buckets.mean() != 0:
            cv2 = float((positive_buckets.std(ddof=1) / positive_buckets.mean()) ** 2)
        else:
            cv2 = 0.0 if len(positive_buckets) == 1 else math.nan
        classification = classify_demand(adi, cv2 if np.isfinite(cv2) else math.inf)
        mean_daily = float(daily.mean())
        std_daily = float(daily.std(ddof=1))
        if classification in {"SMOOTH", "ERRATICO"}:
            raw_level = mean_daily * horizon + Z_NIVEL_SERVICIO * std_daily * math.sqrt(horizon)
            level_method = "PARAMETRICO"
        else:
            rolling = daily.rolling(horizon).sum().dropna()
            raw_level = float(rolling.quantile(NIVEL_SERVICIO)) if len(rolling) else 0.0
            level_method = "PERCENTIL_EMPIRICO"
        records.append(
            {
                "llave_canonica": key,
                "consumo_12m": float(daily.sum()),
                "consumo_quincenal_promedio": float(buckets.mean()),
                "consumo_quincenal_std": float(buckets.std(ddof=1)),
                "consumo_diario_promedio": mean_daily,
                "consumo_diario_std": std_daily,
                "adi": adi,
                "cv2": cv2,
                "clasificacion": classification,
                "motores_implicitos": float(daily.sum() / 2),
                "nivel_objetivo_sin_redondear": raw_level,
                "nivel_objetivo": ceil_even(raw_level),
                "metodo_nivel": level_method,
            }
        )
    return pd.DataFrame(records)


def substitution_metrics(window: pd.DataFrame) -> pd.DataFrame:
    data = window.copy()
    order = data["ordencompra"].fillna("").astype(str).str.strip()
    data["evento"] = np.where(
        order.ne(""),
        "OC|" + order,
        "FECHA|" + data["fecha"].dt.strftime("%Y-%m-%d"),
    )
    positive = data[data["cantidad"] > 0].copy()
    event_stats = (
        positive.groupby(["parser_llave_canonica", "evento"])
        .agg(marcas=("sufijo", "nunique"), unidades=("cantidad", "sum"))
        .reset_index()
    )
    mixed = event_stats[event_stats["marcas"] > 1]
    result = (
        mixed.groupby("parser_llave_canonica")
        .agg(
            eventos_sustitucion=("evento", "nunique"),
            unidades_en_eventos_sustitucion=("unidades", "sum"),
        )
        .reset_index()
        .rename(columns={"parser_llave_canonica": "llave_canonica"})
    )
    totals = (
        positive.groupby("parser_llave_canonica")
        .agg(
            unidades_positivas=("cantidad", "sum"),
            unidades_otra_marca=("cantidad", lambda x: x[data.loc[x.index, "sufijo"].ne("SKF")].sum()),
        )
        .reset_index()
        .rename(columns={"parser_llave_canonica": "llave_canonica"})
    )
    result = totals.merge(result, on="llave_canonica", how="left")
    result["pct_volumen_otra_marca"] = np.where(
        result["unidades_positivas"] > 0,
        100 * result["unidades_otra_marca"] / result["unidades_positivas"],
        0.0,
    )
    return result.fillna({"eventos_sustitucion": 0, "unidades_en_eventos_sustitucion": 0})


def recent_costs(parsed_all: pd.DataFrame) -> pd.DataFrame:
    data = parsed_all[parsed_all["parser_ok"] & parsed_all["costo"].notna()].copy()
    data["preferencia_marca"] = np.where(data["sufijo"].eq("SKF"), 0, 1)
    data = data.sort_values(
        ["parser_llave_canonica", "preferencia_marca", "fecha", "sales_line_key"],
        ascending=[True, True, False, False],
    )
    return (
        data.drop_duplicates("parser_llave_canonica")
        .rename(
            columns={
                "parser_llave_canonica": "llave_canonica",
                "costo": "costo_unitario_reciente",
                "fecha": "fecha_costo_reciente",
                "sufijo": "marca_costo_reciente",
                "idproducto": "codigo_costo_reciente",
            }
        )[
            [
                "llave_canonica",
                "costo_unitario_reciente",
                "fecha_costo_reciente",
                "marca_costo_reciente",
                "codigo_costo_reciente",
            ]
        ]
    )


def policy(row: pd.Series) -> str:
    if row["clasificacion"] == "SMOOTH":
        return "REPOSICION_QUINCENAL"
    if row["clasificacion"] in {"ERRATICO", "INTERMITENTE"}:
        return "REPOSICION_POR_AVISO"
    if row["clasificacion"] == "LUMPY" and row["consumo_12m"] < 4:
        return "BAJO_DEMANDA"
    return "REPOSICION_POR_AVISO"


def verdict(row: pd.Series) -> str:
    suggested = row.get("unidades_sugeridas_cliente")
    objective = row.get("nivel_objetivo")
    if pd.isna(suggested):
        return "SUBIR" if objective > 0 else "EXCLUIR"
    if row["politica_reposicion"] == "BAJO_DEMANDA" or row["consumo_12m"] <= 0:
        return "EXCLUIR"
    if objective > suggested:
        return "SUBIR"
    if objective < suggested:
        return "BAJAR"
    return "ACEPTAR"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sales = load_sales()
    parsed_all = add_parser_columns(sales)
    max_date = sales["fecha"].max().normalize()
    window_start = max_date - pd.DateOffset(months=VENTANA_MESES) + pd.Timedelta(days=1)

    bearing_name = sales["nombreproducto"].fillna("").str.upper().str.startswith("RODAMIENTO")
    rigid_ball = sales["nombreproducto"].fillna("").str.upper().eq("RODAMIENTO RIGIDO DE BOLAS")
    included = parsed_all["parser_ok"] & rigid_ball

    exclusions = parsed_all[bearing_name & ~included].copy()
    exclusions["motivo_exclusion"] = np.select(
        [
            exclusions["parser_error"].eq("ANILLO_NR_EXCLUIDO"),
            exclusions["nombreproducto"].str.upper().str.contains("AGUJA", na=False),
            exclusions["nombreproducto"].str.upper().str.contains("MARCHA LIBRE", na=False),
            exclusions["nombreproducto"].str.upper().str.contains("CONIC", na=False),
            exclusions["nombreproducto"].str.upper().str.contains("ESFERIC|ROTULA", na=False),
            exclusions["prefijo_1"].fillna("").str.match(r"^64\d{2}"),
            ~exclusions["nombreproducto"].str.upper().eq("RODAMIENTO RIGIDO DE BOLAS"),
        ],
        ["ANILLO_NR", "AGUJAS", "MARCHA_LIBRE", "RODILLOS_CONICOS",
         "RODILLOS_ESFERICOS", "SERIE_64XX", "OTRO_TIPO_RODAMIENTO"],
        default="PARSER_NO_CLASIFICADO",
    )
    exclusions["margen_linea"] = np.where(
        exclusions["cantidad"].ne(0),
        exclusions["neto"] - exclusions["costo"] * exclusions["cantidad"],
        0.0,
    )
    excluded_summary = (
        exclusions.groupby(
            ["motivo_exclusion", "prefijo_1", "sufijo", "nombreproducto"], dropna=False
        )
        .agg(
            volumen_neto=("cantidad", "sum"),
            margen_total=("margen_linea", "sum"),
            lineas=("sales_line_key", "count"),
        )
        .reset_index()
        .sort_values(["volumen_neto", "lineas"], ascending=False)
    )
    excluded_summary.to_csv(OUTPUT_DIR / "01_referencias_excluidas.csv", index=False)

    parser_failures = parsed_all[
        rigid_ball & ~parsed_all["parser_ok"]
    ].copy()
    parser_failure_summary = (
        parser_failures.groupby(["prefijo_1", "parser_error"], dropna=False)
        .agg(volumen_neto=("cantidad", "sum"), lineas=("sales_line_key", "count"))
        .reset_index()
        .sort_values(["volumen_neto", "lineas"], ascending=False)
    )
    parser_failure_summary.to_csv(OUTPUT_DIR / "02_fallos_parser.csv", index=False)

    eligible_all = parsed_all[included].copy()
    eligible_window = eligible_all[
        eligible_all["fecha"].between(window_start, max_date)
    ].copy()

    metrics = demand_metrics(eligible_window, window_start, max_date)
    bucket_count = math.ceil((max_date - window_start).days / CICLO_REPOSICION_DIAS) + 1
    bucket_grid = pd.MultiIndex.from_product(
        [
            sorted(eligible_window["parser_llave_canonica"].unique()),
            range(bucket_count),
        ],
        names=["llave_canonica", "cubeta_numero"],
    ).to_frame(index=False)
    eligible_window["cubeta_numero"] = (
        (eligible_window["fecha"] - window_start).dt.days // CICLO_REPOSICION_DIAS
    )
    bucket_actual = (
        eligible_window.groupby(["parser_llave_canonica", "cubeta_numero"])["cantidad"]
        .sum()
        .rename("unidades_netas")
        .reset_index()
        .rename(columns={"parser_llave_canonica": "llave_canonica"})
    )
    bucket_detail = bucket_grid.merge(
        bucket_actual, on=["llave_canonica", "cubeta_numero"], how="left"
    ).fillna({"unidades_netas": 0})
    bucket_detail["fecha_inicio"] = (
        window_start
        + pd.to_timedelta(bucket_detail["cubeta_numero"] * CICLO_REPOSICION_DIAS, unit="D")
    )
    bucket_detail["fecha_fin"] = (
        bucket_detail["fecha_inicio"] + pd.Timedelta(days=CICLO_REPOSICION_DIAS - 1)
    ).clip(upper=max_date)
    bucket_detail.to_csv(OUTPUT_DIR / "03a_consumo_por_cubeta_14d.csv", index=False)
    substitutions = substitution_metrics(eligible_window)
    substitutions.to_csv(OUTPUT_DIR / "04_sustituciones.csv", index=False)

    from io import StringIO

    client_list = pd.read_csv(StringIO(LISTA_CLIENTE_CSV))
    client_parsed = pd.DataFrame(
        client_list["referencia"].map(normalize_designation).tolist(),
        index=client_list.index,
    )
    client_list = pd.concat([client_list, client_parsed.add_prefix("parser_")], axis=1)
    if not client_list["parser_ok"].all():
        failures = client_list.loc[~client_list["parser_ok"], ["referencia", "parser_error"]]
        raise ValueError(f"Fallos al parsear anexo:\n{failures.to_string(index=False)}")
    client_agg = (
        client_list.groupby("parser_llave_canonica")
        .agg(
            unidades_sugeridas_cliente=("unidades", "sum"),
            lineas_anexo=("referencia", "size"),
            referencias_anexo=("referencia", lambda x: "|".join(x)),
        )
        .reset_index()
        .rename(columns={"parser_llave_canonica": "llave_canonica"})
    )

    main_table = (
        metrics.merge(substitutions, on="llave_canonica", how="left")
        .merge(client_agg, on="llave_canonica", how="outer")
        .merge(recent_costs(eligible_all), on="llave_canonica", how="left")
    )
    metric_numeric = [
        "consumo_12m", "consumo_quincenal_promedio", "consumo_quincenal_std",
        "consumo_diario_promedio", "consumo_diario_std", "motores_implicitos",
        "nivel_objetivo", "unidades_positivas", "unidades_otra_marca",
        "eventos_sustitucion", "unidades_en_eventos_sustitucion",
        "pct_volumen_otra_marca",
    ]
    for column in metric_numeric:
        if column in main_table:
            main_table[column] = main_table[column].fillna(0)
    main_table["dias_cobertura_sugerida"] = np.where(
        main_table["consumo_diario_promedio"] > 0,
        main_table["unidades_sugeridas_cliente"] / main_table["consumo_diario_promedio"],
        np.nan,
    )
    main_table["delta_objetivo_menos_sugerido"] = (
        main_table["nivel_objetivo"] - main_table["unidades_sugeridas_cliente"].fillna(0)
    )
    main_table["valor_costo_sugerido"] = (
        main_table["unidades_sugeridas_cliente"].fillna(0)
        * main_table["costo_unitario_reciente"]
    )
    main_table["valor_costo_objetivo"] = (
        main_table["nivel_objetivo"] * main_table["costo_unitario_reciente"]
    )
    main_table["politica_reposicion"] = main_table.apply(policy, axis=1)
    main_table["veredicto"] = main_table.apply(verdict, axis=1)
    main_table["unidades_propuestas_finales"] = np.where(
        main_table["veredicto"].eq("EXCLUIR"), 0, main_table["nivel_objetivo"]
    )
    main_table["valor_costo_propuesto_final"] = (
        main_table["unidades_propuestas_finales"]
        * main_table["costo_unitario_reciente"]
    )
    main_table = main_table.sort_values("valor_costo_sugerido", ascending=False, na_position="last")
    main_table.to_csv(OUTPUT_DIR / "03_tabla_principal.csv", index=False)

    gaps = main_table[
        main_table["unidades_sugeridas_cliente"].isna() & main_table["consumo_12m"].gt(0)
    ].sort_values("consumo_12m", ascending=False)
    gaps.to_csv(OUTPUT_DIR / "05_huecos.csv", index=False)

    # Sin histórico: 12 meses y comprobación explícita a 24/36 meses.
    history_horizons = client_agg[["llave_canonica", "unidades_sugeridas_cliente"]].copy()
    for months in (12, 24, 36):
        start = max_date - pd.DateOffset(months=months) + pd.Timedelta(days=1)
        totals = (
            eligible_all[eligible_all["fecha"].between(start, max_date)]
            .groupby("parser_llave_canonica")["cantidad"]
            .sum()
        )
        history_horizons[f"consumo_{months}m"] = history_horizons["llave_canonica"].map(totals).fillna(0)
    no_history = history_horizons[history_horizons["consumo_12m"].eq(0)]
    no_history.to_csv(OUTPUT_DIR / "06_sin_historico.csv", index=False)

    # Tendencia: años completos observados y 2026 anualizado con días transcurridos.
    eligible_all["anio"] = eligible_all["fecha"].dt.year
    trend_size = (
        eligible_all.groupby(["anio", "parser_tamano"])["cantidad"]
        .sum()
        .reset_index(name="unidades")
        .rename(columns={"parser_tamano": "tamano"})
    )
    days_2026 = max_date.dayofyear
    trend_size["factor_anualizacion"] = np.where(
        trend_size["anio"].eq(max_date.year), 365 / days_2026, 1.0
    )
    trend_size["unidades_anualizadas"] = trend_size["unidades"] * trend_size["factor_anualizacion"]
    trend_size.to_csv(OUTPUT_DIR / "07_tendencia_por_tamano.csv", index=False)
    trend_total = (
        trend_size.groupby("anio")
        .agg(unidades=("unidades", "sum"), unidades_anualizadas=("unidades_anualizadas", "sum"))
        .reset_index()
    )
    trend_total.to_csv(OUTPUT_DIR / "08_tendencia_total.csv", index=False)

    # Margen anual de unidades no SKF en ventana, usando margen real neto de esas líneas.
    other_brand = eligible_window[(eligible_window["sufijo"] != "SKF") & (eligible_window["cantidad"] != 0)].copy()
    other_brand["margen_linea"] = (
        other_brand["neto"] - other_brand["costo"] * other_brand["cantidad"]
    )
    summary = pd.DataFrame(
        [
            {
                "fecha_maxima": max_date.date().isoformat(),
                "inicio_ventana_12m": window_start.date().isoformat(),
                "capital_sugerido": main_table["valor_costo_sugerido"].sum(min_count=1),
                "capital_propuesto": main_table["valor_costo_propuesto_final"].sum(min_count=1),
                "skus_sugeridos": int(main_table["unidades_sugeridas_cliente"].notna().sum()),
                "skus_propuestos": int((main_table["unidades_propuestas_finales"] > 0).sum()),
                "skus_conteo_quincenal": int(
                    (main_table["unidades_propuestas_finales"] > 0).sum()
                ),
                "unidades_otra_marca_12m": other_brand["cantidad"].sum(),
                "margen_anual_estimado_unidades_otra_marca": other_brand["margen_linea"].sum(),
                "lineas_dcc_ventana": int((eligible_window["prefijo"] == "DCC").sum()),
                "cantidad_dcc_ventana": eligible_window.loc[
                    eligible_window["prefijo"] == "DCC", "cantidad"
                ].sum(),
                "fallos_parser": len(parser_failure_summary),
            }
        ]
    )
    summary.to_csv(OUTPUT_DIR / "09_resumen_ejecutivo.csv", index=False)

    validation = eligible_all[
        eligible_all["prefijo"].eq("SC2") & eligible_all["numero"].eq(251991)
        & eligible_all["parser_tamano"].isin(["6204", "6205"])
        & eligible_all["parser_sello"].eq("CAUCHO")
    ].sort_values(["parser_tamano", "sufijo"])[
        ["fecha", "prefijo", "numero", "prefijo_1", "sufijo", "cantidad",
         "parser_llave_canonica"]
    ]
    validation.to_csv(OUTPUT_DIR / "10_validacion_sc2_251991.csv", index=False)

    print(f"Base leída: {DB_PATH}")
    print(f"Ventana: {window_start.date()} a {max_date.date()}")
    print(f"Filas cliente: {len(sales):,}; elegibles 12m: {len(eligible_window):,}")
    print(f"CSV generados en: {OUTPUT_DIR}")
    print(f"Fallos parser (referencias): {len(parser_failure_summary)}")
    if len(parser_failure_summary):
        print(parser_failure_summary.to_string(index=False))
    print("\nValidación SC2-251991:")
    print(validation.to_string(index=False))
    print("\nResumen:")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
