"""Construye y ejecuta el análisis del convenio MYM, bodega 59."""

from __future__ import annotations

import os
import re
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "notebooks" / "convenio_mym_bodega59.ipynb"
REQUEST = Path(
    "/Users/ricardolugo/.codex/attachments/"
    "9c5462cf-da33-4723-8e57-aa68e0d77081/pasted-text.txt"
)


def md(value: str):
    return nbf.v4.new_markdown_cell(value.strip())


def code(value: str):
    return nbf.v4.new_code_cell(value.strip())


def agreement_csv() -> str:
    text = REQUEST.read_text(encoding="utf-8")
    blocks = re.findall(r"```csv\n(.*?)```", text, flags=re.DOTALL)
    if not blocks:
        raise RuntimeError("No se encontró el anexo CSV del acuerdo.")
    return blocks[-1].strip()


def notebook():
    agreement = agreement_csv()
    nb = nbf.v4.new_notebook()
    nb["metadata"]["kernelspec"] = {
        "display_name": "Python 3", "language": "python", "name": "python3",
    }
    nb["metadata"]["language_info"] = {"name": "python", "version": "3.12"}
    nb["cells"] = [
        md(
            """
# Convenio de consignación vigente — MYM BOBINADOS, bodega 59

Diagnóstico del funcionamiento, uso, nivel pactado y retorno del convenio. El análisis
trabaja en modo lectura y cruza ventas, snapshots mensuales y el acuerdo exacto SKF.

La identidad principal es el `idproducto` exacto porque el acuerdo distingue variantes
con y sin grasa GJN. La llave canónica solo se utiliza como apoyo para detectar compras
equivalentes de otra marca.
"""
        ),
        md(
            """
## Parámetros y acuerdo pactado

Las reglas de decisión son visibles y ajustables. La cobertura objetivo conserva la
regla simple usada para SERMOTOR.
"""
        ),
        code(
            f'''
from io import StringIO
from pathlib import Path
import math
import sqlite3
import numpy as np
import pandas as pd
from IPython.display import display

from scripts.analyze_sermotor_consignacion import normalize_designation, ceil_even

IDBODEGA = 59
DB_PATH = Path("database/commercial.db")
MESES_COBERTURA_OBJETIVO = 2.5
COBERTURA_BAJA_MESES = 2.0
COBERTURA_ALTA_MESES = 8.0

ACUERDO_CSV = """{agreement}"""
acuerdo = pd.read_csv(StringIO(ACUERDO_CSV), dtype={{"codigo": str}})
acuerdo["codigo"] = acuerdo["codigo"].str.strip()
assert not acuerdo["codigo"].duplicated().any()

pd.set_option("display.max_rows", 250)
pd.set_option("display.max_columns", 60)
PESO = "${{:,.0f}}".format
''',
        ),
        md(
            """
## Paso 0 — Identidad y calidad de datos

Se verifica el cliente dominante, los cruces exactos del acuerdo y las fechas efectivas
de snapshot. Un mes ausente no se interpola ni se inventa.
"""
        ),
        code(
            """
uri = f"file:{DB_PATH}?mode=ro"
with sqlite3.connect(uri, uri=True) as con:
    ventas = pd.read_sql_query(
        "SELECT * FROM raw_sales WHERE CAST(idbodega AS TEXT)=?",
        con, params=(str(IDBODEGA),),
    )
    inventario = pd.read_sql_query(
        "SELECT * FROM inventario_snapshot WHERE CAST(idbodega AS TEXT)=?",
        con, params=(str(IDBODEGA),),
    )

ventas["fecha"] = pd.to_datetime(ventas["fecha"], errors="raise")
inventario["fecha_snapshot"] = pd.to_datetime(
    inventario["fecha_snapshot"], errors="raise"
)
identidad = (
    ventas.groupby(["nit", "razonsocial"], dropna=False)
    .agg(lineas=("idproducto", "size"), fecha_min=("fecha", "min"),
         fecha_max=("fecha", "max"))
    .reset_index().sort_values("lineas", ascending=False)
)
display(identidad)

fechas_snapshot = sorted(inventario["fecha_snapshot"].dropna().unique())
calendario = pd.DataFrame({"fecha_snapshot": fechas_snapshot})
calendario["mes"] = calendario["fecha_snapshot"].dt.strftime("%Y-%m")
esperados = pd.date_range(
    calendario["fecha_snapshot"].min(),
    calendario["fecha_snapshot"].max(), freq="MS",
)
faltantes = sorted(set(esperados) - set(fechas_snapshot))
display(calendario)
print("Meses faltantes:", ", ".join(pd.Timestamp(x).strftime("%Y-%m") for x in faltantes) or "Ninguno")

sales_codes = set(ventas["idproducto"].dropna().astype(str))
inventory_codes = set(inventario["idproducto"].dropna().astype(str))
cruce = acuerdo.assign(
    existe_ventas=acuerdo["codigo"].isin(sales_codes),
    existe_inventario=acuerdo["codigo"].isin(inventory_codes),
)
no_cruzan = cruce[~cruce["existe_ventas"] | ~cruce["existe_inventario"]]
display(no_cruzan)
print(
    f"Acuerdo: {len(acuerdo)} referencias; "
    f"sin cruce completo: {len(no_cruzan)}."
)
"""
        ),
        md(
            """
## Bloque A — ¿El proceso funciona?

Sin movimientos de traslado no existe una medición independiente del consumo implícito:
la reposición es una incógnita. Para no fingir precisión, se muestran tres cantidades:

- **Consumo sin reposición:** stock inicial menos stock final.
- **Facturado:** ventas netas de la bodega durante el intervalo.
- **Reposición implícita:** facturado + stock final − stock inicial; es la reposición
  necesaria para reconciliar ambos datos.

Una reposición implícita negativa se marca como brecha porque apunta a transferencias,
ajustes, mermas, devoluciones o diferencias de corte.

Con reposición semanal, un inventario plano o cercano al pactado **no es evidencia de
sobrestock**. Las columnas de ceros e inventario medio frente al pacto se conservan
únicamente para diagnosticar si el proceso de reposición parece cumplirse. Los snapshots
mensuales no permiten comprobar el comportamiento semana a semana.
"""
        ),
        code(
            """
start = calendario["fecha_snapshot"].min()
end = calendario["fecha_snapshot"].max()
ventas_periodo = ventas[ventas["fecha"].ge(start) & ventas["fecha"].lt(end)].copy()

stock = inventario.pivot_table(
    index="idproducto", columns="fecha_snapshot", values="unidades",
    aggfunc="sum", fill_value=0,
)
intervalos = []
for left, right in zip(fechas_snapshot[:-1], fechas_snapshot[1:]):
    sold = (
        ventas[ventas["fecha"].ge(left) & ventas["fecha"].lt(right)]
        .groupby("idproducto")["cantidad"].sum()
    )
    keys = stock.index.union(sold.index)
    s0 = stock[left].reindex(keys, fill_value=0)
    s1 = stock[right].reindex(keys, fill_value=0)
    billed = sold.reindex(keys, fill_value=0)
    part = pd.DataFrame({
        "periodo": f"{pd.Timestamp(left):%Y-%m-%d} → {pd.Timestamp(right):%Y-%m-%d}",
        "idproducto": keys,
        "stock_inicial": s0.values,
        "stock_final": s1.values,
        "consumo_sin_reposicion": (s0 - s1).values,
        "facturado": billed.values,
        "reposicion_implicita": (billed + s1 - s0).values,
    })
    part["brecha_sin_reposicion"] = (
        part["consumo_sin_reposicion"] - part["facturado"]
    )
    intervalos.append(part)
movimientos = pd.concat(intervalos, ignore_index=True)
resumen_intervalos = (
    movimientos.groupby("periodo")
    .agg(
        stock_inicial=("stock_inicial", "sum"),
        stock_final=("stock_final", "sum"),
        consumo_sin_reposicion=("consumo_sin_reposicion", "sum"),
        facturado=("facturado", "sum"),
        reposicion_implicita=("reposicion_implicita", "sum"),
        brecha_sin_reposicion=("brecha_sin_reposicion", "sum"),
        referencias_reposicion_negativa=(
            "reposicion_implicita", lambda x: int((x < 0).sum())
        ),
    ).reset_index()
)
display(resumen_intervalos)

acuerdo_stock = stock.reindex(acuerdo["codigo"]).fillna(0)
ventas_por_codigo = ventas_periodo.groupby("idproducto")["cantidad"].sum()
zero_counts = (acuerdo_stock == 0).sum(axis=1)
flat = pd.DataFrame({
    "codigo": acuerdo["codigo"],
    "stock_inicial": acuerdo["codigo"].map(acuerdo_stock.iloc[:, 0]),
    "stock_final": acuerdo["codigo"].map(acuerdo_stock.iloc[:, -1]),
    "desviacion_snapshots": acuerdo["codigo"].map(acuerdo_stock.std(axis=1)),
    "consumo_facturado": acuerdo["codigo"].map(ventas_por_codigo).fillna(0),
    "veces_en_cero": acuerdo["codigo"].map(zero_counts).fillna(
        len(fechas_snapshot)
    ).astype(int),
    "inventario_promedio": acuerdo["codigo"].map(
        acuerdo_stock.mean(axis=1)
    ).fillna(0),
})
flat = flat.merge(
    acuerdo[["codigo", "unidades_pactadas"]], on="codigo", how="left"
)
flat["inventario_medio_vs_pactado"] = np.where(
    flat["unidades_pactadas"] > 0,
    flat["inventario_promedio"] / flat["unidades_pactadas"], np.nan,
)
flat["senal"] = np.select(
    [
        flat["consumo_facturado"].gt(0)
        & flat["inventario_promedio"].eq(0),
        flat["consumo_facturado"].gt(0)
        & flat["desviacion_snapshots"].fillna(0).eq(0),
    ],
    [
        "VENTA_SIN_CRUCE_INVENTARIO",
        "STOCK_PLANO_COMPATIBLE_REPOSICION_SEMANAL",
    ],
    default="SIN_ALERTA",
)
display(flat[flat["senal"] != "SIN_ALERTA"])
"""
        ),
        md(
            """
## Bloque B — ¿Se usa lo que está en la bodega?

La rotación se anualiza según los días realmente observados entre el primer y último
snapshot. El capital usa unidades físicas y costo promedio del snapshot más reciente.
"""
        ),
        code(
            """
days_observed = max((end - start).days, 1)
annual_factor = 365.25 / days_observed
latest_date = inventario["fecha_snapshot"].max()
latest = (
    inventario[inventario["fecha_snapshot"].eq(latest_date)]
    .sort_values("fecha_carga").drop_duplicates("idproducto", keep="last")
    .set_index("idproducto")
)
with sqlite3.connect(uri, uri=True) as con:
    costos_inventario = pd.read_sql_query(
        "SELECT idproducto, costo_unitario, fecha_snapshot, fecha_carga "
        "FROM inventario_snapshot WHERE costo_unitario IS NOT NULL", con,
    )
    costos_ventas = pd.read_sql_query(
        "SELECT idproducto, costo, fecha FROM raw_sales WHERE costo IS NOT NULL", con,
    )
costos_inventario["fecha_snapshot"] = pd.to_datetime(
    costos_inventario["fecha_snapshot"], errors="coerce"
)
costo_inv_actual = (
    costos_inventario.sort_values(["fecha_snapshot", "fecha_carga"])
    .drop_duplicates("idproducto", keep="last").set_index("idproducto")["costo_unitario"]
)
costos_ventas["fecha"] = pd.to_datetime(costos_ventas["fecha"], errors="coerce")
costo_venta_reciente = (
    costos_ventas.sort_values("fecha").drop_duplicates("idproducto", keep="last")
    .set_index("idproducto")["costo"]
)
avg_inventory = inventario.groupby("idproducto")["unidades"].mean()
first_inventory = (
    inventario[inventario["fecha_snapshot"].eq(start)]
    .groupby("idproducto")["unidades"].sum()
)
last_inventory = (
    inventario[inventario["fecha_snapshot"].eq(end)]
    .groupby("idproducto")["unidades"].sum()
)

uso = acuerdo[["codigo", "unidades_pactadas"]].copy()
uso["consumo_periodo"] = uso["codigo"].map(ventas_por_codigo).fillna(0)
uso["consumo_anualizado"] = uso["consumo_periodo"] * annual_factor
uso["inventario_promedio"] = uso["codigo"].map(avg_inventory).fillna(0)
uso["rotaciones_anualizadas"] = np.where(
    uso["inventario_promedio"] > 0,
    uso["consumo_anualizado"] / uso["inventario_promedio"], np.nan,
)
uso["inventario_inicial"] = uso["codigo"].map(first_inventory).fillna(0)
uso["inventario_final"] = uso["codigo"].map(last_inventory).fillna(0)
uso["inventario_sin_cambio"] = uso["inventario_inicial"].eq(uso["inventario_final"])
uso["costo_actual"] = uso["codigo"].map(costo_inv_actual)
uso["fuente_costo_actual"] = np.where(
    uso["costo_actual"].notna(), "ÚLTIMO_SNAPSHOT_EMPRESA", "ÚLTIMA_VENTA"
)
uso["costo_actual"] = uso["costo_actual"].fillna(
    uso["codigo"].map(costo_venta_reciente)
)
assert uso["costo_actual"].notna().all(), "Hay referencias pactadas sin costo actual"
uso["capital_comprometido_ref"] = (
    uso["unidades_pactadas"] * uso["costo_actual"]
)
display(uso.sort_values("rotaciones_anualizadas", na_position="first"))

capital_total = uso["capital_comprometido_ref"].sum()
capital_lento = uso.loc[
    uso["rotaciones_anualizadas"].fillna(0).lt(1), "capital_comprometido_ref"
].sum()
print(
    "Capital comprometido en referencias con rotación < 1x/año:",
    PESO(capital_lento),
    f"({capital_lento / capital_total:.1%} del capital del acuerdo)"
    if capital_total else "(sin capital)",
)
"""
        ),
        md(
            """
## Bloque C — ¿Es correcta la cantidad pactada?

El nivel diagnóstico equivale a 2,5 meses de consumo anualizado, redondeado hacia arriba
a número par. El veredicto se decide exclusivamente por la cobertura del nivel pactado:
menos de 2 meses implica **SUBIR**, entre 2 y 8 meses **MANTENER**, y más de 8 meses
**BAJAR**. El consumo cero conserva el corte duro **RETIRAR**.

El inventario observado y los snapshots en cero no participan en esta decisión porque
la reposición semanal tiende a devolver el stock al nivel pactado.
"""
        ),
        code(
            """
monthly_factor = 12 * days_observed / 365.25
monthly_factor = max(monthly_factor, 1)
metricas = uso.copy()
metricas["consumo_mensual"] = metricas["consumo_periodo"] / monthly_factor
metricas["meses_cobertura"] = np.where(
    metricas["consumo_mensual"] > 0,
    metricas["unidades_pactadas"] / metricas["consumo_mensual"], np.nan,
)
metricas["nivel_simple"] = (
    metricas["consumo_mensual"] * MESES_COBERTURA_OBJETIVO
).map(ceil_even)
metricas["veces_en_cero"] = metricas["codigo"].map(zero_counts).fillna(
    len(fechas_snapshot)
).astype(int)
metricas["inventario_maximo"] = metricas["codigo"].map(
    acuerdo_stock.max(axis=1)
).fillna(0)
metricas["inventario_medio_vs_pactado"] = np.where(
    metricas["unidades_pactadas"] > 0,
    metricas["inventario_promedio"] / metricas["unidades_pactadas"], np.nan,
)

def verdict(row):
    if row["consumo_periodo"] <= 0:
        return "RETIRAR"
    if row["meses_cobertura"] < COBERTURA_BAJA_MESES:
        return "SUBIR"
    if row["meses_cobertura"] > COBERTURA_ALTA_MESES:
        return "BAJAR"
    return "MANTENER"

def reason(row):
    if row["veredicto"] == "RETIRAR":
        return (
            f"Sin consumo entre {start:%Y-%m-%d} y {end:%Y-%m-%d}; "
            "retiro por corte duro de consumo cero."
        )
    if row["veredicto"] == "SUBIR":
        return (
            f"Cobertura pactada {row['meses_cobertura']:.2f} meses, menor que "
            f"el umbral de {COBERTURA_BAJA_MESES:.0f} meses."
        )
    if row["veredicto"] == "BAJAR":
        return (
            f"Cobertura pactada {row['meses_cobertura']:.2f} meses, mayor que "
            f"el umbral de {COBERTURA_ALTA_MESES:.0f} meses."
        )
    return (
        f"Cobertura pactada {row['meses_cobertura']:.2f} meses, dentro del "
        f"rango de {COBERTURA_BAJA_MESES:.0f} a "
        f"{COBERTURA_ALTA_MESES:.0f} meses."
    )

metricas["veredicto"] = metricas.apply(verdict, axis=1)
metricas["motivo"] = metricas.apply(reason, axis=1)
metricas["unidades_propuestas"] = np.select(
    [
        metricas["veredicto"].eq("RETIRAR"),
        metricas["veredicto"].isin(["BAJAR", "SUBIR"]),
    ],
    [0, metricas["nivel_simple"]],
    default=metricas["unidades_pactadas"],
).astype(int)
metricas["capital_propuesto_ref"] = (
    metricas["unidades_propuestas"] * metricas["costo_actual"]
)
display(
    metricas.sort_values(
        ["veredicto", "capital_comprometido_ref"], ascending=[True, False]
    )
)
"""
        ),
        md(
            """
## Bloque D — ¿Qué sobra y qué falta?

Se separan cuatro conversaciones: retiros, compras del cliente desde otras bodegas,
equivalentes de otra marca y referencias consumidas en la bodega 59 fuera del acuerdo.
"""
        ),
        code(
            """
print("Candidatas a retirar")
display(metricas[metricas["veredicto"].eq("RETIRAR")][
    ["codigo", "unidades_pactadas", "inventario_promedio",
     "capital_comprometido_ref", "motivo"]
])

dominant_nit = str(identidad.groupby("nit")["lineas"].sum().idxmax())
with sqlite3.connect(uri, uri=True) as con:
    ventas_cliente = pd.read_sql_query(
        "SELECT * FROM raw_sales WHERE CAST(nit AS TEXT)=?", con,
        params=(dominant_nit,),
    )
ventas_cliente["fecha"] = pd.to_datetime(ventas_cliente["fecha"], errors="raise")
cliente_periodo = ventas_cliente[
    ventas_cliente["fecha"].ge(start) & ventas_cliente["fecha"].lt(end)
].copy()
otras_bodegas = cliente_periodo[
    cliente_periodo["idbodega"].astype(str).ne(str(IDBODEGA))
]
compras_fuera = (
    otras_bodegas.groupby(["idproducto", "nombreproducto"])
    .agg(unidades=("cantidad", "sum"), documentos=("numero", "nunique"),
         bodegas=("idbodega", lambda x: ",".join(sorted(set(map(str, x))))))
    .reset_index().sort_values("unidades", ascending=False)
)
display(compras_fuera[compras_fuera["unidades"] > 0].head(100))

agreement_parsed = pd.DataFrame(
    acuerdo["codigo"].map(normalize_designation).tolist(), index=acuerdo.index
)
agreement_keys = set(agreement_parsed.loc[
    agreement_parsed["ok"].fillna(False), "llave_canonica"
])
sales_parsed = pd.DataFrame(
    cliente_periodo["prefijo_1"].map(normalize_designation).tolist(),
    index=cliente_periodo.index,
).add_prefix("parser_")
cliente_norm = pd.concat([cliente_periodo, sales_parsed], axis=1)
otras_marcas = cliente_norm[
    cliente_norm["parser_llave_canonica"].isin(agreement_keys)
    & cliente_norm["sufijo"].fillna("").ne("SKF")
]
substituciones = (
    otras_marcas.groupby(
        ["parser_llave_canonica", "sufijo", "idproducto"], dropna=False
    )["cantidad"].sum().reset_index(name="unidades")
    .sort_values("unidades", ascending=False)
)
display(substituciones[substituciones["unidades"] > 0])

consumo_59 = (
    ventas_periodo.groupby(["idproducto", "nombreproducto"])["cantidad"]
    .sum().reset_index(name="unidades")
)
fuera_acuerdo = consumo_59[
    ~consumo_59["idproducto"].isin(set(acuerdo["codigo"]))
    & consumo_59["unidades"].gt(0)
].sort_values("unidades", ascending=False)
display(fuera_acuerdo.head(100))
"""
        ),
        md(
            """
## Bloque E — Facturación, capital comprometido y escenario antes/después

La referencia financiera única del convenio es el **capital comprometido**:
`unidades pactadas × costo actual`. El costo actual se toma del snapshot más reciente
disponible en la empresa y, si la referencia no aparece en inventario, de su venta más
reciente.

El inventario físico promedio observado se informa aparte como métrica operativa; no se
usa como denominador de rotación o retorno. Julio contiene información hasta la última
fecha disponible en ventas y por ello puede ser un mes parcial.
"""
        ),
        code(
            """
ventas_fin = ventas[
    ventas["fecha"].ge(pd.Timestamp("2026-01-01"))
    & ventas["fecha"].lt(pd.Timestamp("2026-08-01"))
].copy()
ventas_fin["mes"] = ventas_fin["fecha"].dt.to_period("M")
ventas_fin["costo_vendido"] = ventas_fin["cantidad"] * ventas_fin["costo"]
mensual = (
    ventas_fin.groupby("mes")
    .agg(
        facturacion_bruta=("neto", "sum"),
        costo_vendido=("costo_vendido", "sum"),
    )
    .reindex(pd.period_range("2026-01", "2026-07", freq="M"), fill_value=0)
)
mensual["margen"] = mensual["facturacion_bruta"] - mensual["costo_vendido"]
mensual.index = mensual.index.astype(str)
mensual.index.name = "mes"
promedio = mensual.mean().to_frame().T
promedio.index = ["PROMEDIO_MENSUAL"]
mensual_con_promedio = pd.concat([mensual, promedio])
display(mensual_con_promedio.style.format({
    "facturacion_bruta": PESO, "costo_vendido": PESO, "margen": PESO,
}))
ultima_fecha_ventas = ventas_fin["fecha"].max()
print(f"Última fecha incluida en julio: {ultima_fecha_ventas:%Y-%m-%d}")

capital_comprometido = metricas["capital_comprometido_ref"].sum()
capital_propuesto = metricas["capital_propuesto_ref"].sum()
capital_liberado = capital_comprometido - capital_propuesto
reduccion_capital = (
    capital_liberado / capital_comprometido if capital_comprometido else np.nan
)
costo_anualizado = mensual["costo_vendido"].mean() * 12
margen_anualizado = mensual["margen"].mean() * 12

inventario["valor_fisico"] = inventario["unidades"] * inventario["costo_unitario"]
valor_fisico_por_snapshot = (
    inventario.groupby("fecha_snapshot")["valor_fisico"].sum().reset_index()
)
inventario_fisico_promedio = valor_fisico_por_snapshot["valor_fisico"].mean()

escenario = pd.DataFrame({
    "Escenario": ["ANTES — pacto vigente", "DESPUÉS — niveles propuestos"],
    "Capital comprometido": [capital_comprometido, capital_propuesto],
    "Rotación anualizada": [
        costo_anualizado / capital_comprometido,
        costo_anualizado / capital_propuesto,
    ],
    "Retorno anualizado": [
        margen_anualizado / capital_comprometido,
        margen_anualizado / capital_propuesto,
    ],
})
display(escenario.style.format({
    "Capital comprometido": PESO,
    "Rotación anualizada": "{:.2f}x",
    "Retorno anualizado": "{:.1%}",
}))

operacion = pd.DataFrame({
    "Métrica operativa (no capital contractual)": [
        "Inventario físico promedio observado",
        "Snapshots incluidos",
    ],
    "Valor": [PESO(inventario_fisico_promedio), str(len(fechas_snapshot))],
})
display(operacion)
display(valor_fisico_por_snapshot.style.format({"valor_fisico": PESO}))

print(
    f"Aplicar los veredictos libera {PESO(capital_liberado)} "
    f"({reduccion_capital:.1%}) de capital comprometido; con el mismo margen "
    f"mensual observado, el retorno anualizado pasa de "
    f"{margen_anualizado / capital_comprometido:.1%} a "
    f"{margen_anualizado / capital_propuesto:.1%}."
)

ventas["anio"] = ventas["fecha"].dt.year
crecimiento = (
    ventas.groupby("anio")
    .agg(unidades=("cantidad", "sum"), ventas_netas=("neto", "sum"),
         lineas=("idproducto", "size"))
    .reset_index()
)
display(crecimiento.style.format({"unidades": "{:,.0f}", "ventas_netas": PESO}))
"""
        ),
        md(
            """
## Tabla consolidada final

Cada fila corresponde a una referencia exacta del acuerdo. El capital comprometido usa
las unidades pactadas; el capital propuesto aplica el veredicto y el nivel simple. La
rotación por referencia y cobertura usan el periodo comparable entre snapshots.
"""
        ),
        code(
            """
final = metricas[[
    "codigo", "unidades_pactadas", "consumo_periodo", "consumo_mensual",
    "meses_cobertura", "veces_en_cero", "inventario_medio_vs_pactado",
    "rotaciones_anualizadas",
    "inventario_promedio", "inventario_final", "costo_actual",
    "capital_comprometido_ref", "unidades_propuestas",
    "capital_propuesto_ref", "veredicto", "motivo",
]].rename(columns={
    "codigo": "Referencia",
    "unidades_pactadas": "Pactado",
    "consumo_periodo": "Consumo 2026 comparable",
    "consumo_mensual": "Consumo mensual",
    "meses_cobertura": "Meses cobertura",
    "veces_en_cero": "Veces en cero",
    "inventario_medio_vs_pactado": "Inventario medio / pactado",
    "rotaciones_anualizadas": "Rotación anualizada",
    "inventario_promedio": "Inventario promedio",
    "inventario_final": "Inventario último snapshot",
    "costo_actual": "Costo actual",
    "capital_comprometido_ref": "Capital comprometido",
    "unidades_propuestas": "Unidades propuestas",
    "capital_propuesto_ref": "Capital propuesto",
    "veredicto": "Veredicto",
    "motivo": "Motivo",
})
orden = {"SUBIR": 0, "RETIRAR": 1, "BAJAR": 2, "MANTENER": 3}
final["_orden"] = final["Veredicto"].map(orden)
final = final.sort_values(
    ["_orden", "Capital comprometido"], ascending=[True, False]
).drop(columns="_orden")
display(final.style.format({
    "Pactado": "{:,.0f}",
    "Consumo 2026 comparable": "{:,.1f}",
    "Consumo mensual": "{:,.1f}",
    "Meses cobertura": "{:,.2f}",
    "Veces en cero": "{:,.0f}",
    "Inventario medio / pactado": "{:.0%}",
    "Rotación anualizada": "{:,.1f}",
    "Inventario promedio": "{:,.1f}",
    "Inventario último snapshot": "{:,.0f}",
    "Costo actual": PESO,
    "Capital comprometido": PESO,
    "Unidades propuestas": "{:,.0f}",
    "Capital propuesto": PESO,
}, na_rep="—"))

resumen_final = (
    final.groupby("Veredicto")
    .agg(referencias=("Referencia", "size"), pactado=("Pactado", "sum"),
         propuesto=("Unidades propuestas", "sum"),
         capital_antes=("Capital comprometido", "sum"),
         capital_despues=("Capital propuesto", "sum"))
    .reindex(["SUBIR", "MANTENER", "BAJAR", "RETIRAR"])
    .dropna(how="all").reset_index()
)
display(resumen_final.style.format({
    "referencias": "{:,.0f}", "pactado": "{:,.0f}", "propuesto": "{:,.0f}",
    "capital_antes": PESO, "capital_despues": PESO,
}))
"""
        ),
        md(
            """
## Exportación opcional

El notebook es el entregable. Active la bandera solo si necesita extraer las tablas.
"""
        ),
        code(
            """
EXPORTAR = False
if EXPORTAR:
    output = Path("outputs/mym_bodega59")
    output.mkdir(parents=True, exist_ok=True)
    final.to_csv(output / "tabla_consolidada.csv", index=False)
    resumen_intervalos.to_csv(output / "reconciliacion_intervalos.csv", index=False)
    fuera_acuerdo.to_csv(output / "fuera_acuerdo.csv", index=False)
    print(f"Exportado en {output.resolve()}")
else:
    print("Exportación desactivada.")
"""
        ),
    ]
    return nb


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/mym-mpl")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    nb = notebook()
    client = NotebookClient(
        nb, timeout=240, kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    nbf.write(nb, OUTPUT)
    print(f"Notebook generado y ejecutado: {OUTPUT}")


if __name__ == "__main__":
    main()
