"""Construye y ejecuta los notebooks entregables de consignación SERMOTOR."""

from __future__ import annotations

import os
import csv
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"


def md(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


def execute_and_save(notebook, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    client = NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    nbf.write(notebook, path)


def initial_notebook():
    nb = nbf.v4.new_notebook()
    nb["metadata"]["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb["metadata"]["language_info"] = {"name": "python", "version": "3.12"}
    nb["cells"] = [
        md(
            """
# Consignación SERMOTOR — nivel inicial y comparativo

Punto de partida para la consignación de rodamientos de SERMOTOR (`nit = 900611187`).
El cálculo usa 12 meses de consumo neto multimarca, incluyendo devoluciones DCC una
sola vez. No utiliza stock de seguridad, ADI, CV² ni percentiles.
"""
        ),
        md(
            """
## 1. Parámetros

Estos cuatro parámetros controlan la recomendación. El costo umbral corresponde al
par completo, no a una unidad.
"""
        ),
        code(
            """
MESES_COBERTURA = 2.5
UMBRAL_PAR      = 100_000
UMBRAL_SELLO    = 0.80
VENTANA_MESES   = 12
NIT             = "900611187"

from pathlib import Path
from io import StringIO
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display

from scripts.analyze_sermotor_consignacion import (
    LISTA_CLIENTE_CSV,
    add_parser_columns,
    ceil_even,
    load_sales,
    normalize_designation,
    recent_costs,
)
from scripts.analyze_sermotor_nivel_inicial import skf_dispatch_reference

pd.set_option("display.max_rows", 200)
pd.set_option("display.max_columns", 50)
PESO = "${:,.0f}".format
"""
        ),
        md(
            """
## 2. Carga y normalización

Se filtra por NIT dentro de la consulta de lectura. El universo analizable contiene
únicamente rodamientos rígidos de bolas 608/60xx/62xx/63xx. El parser separa tamaño,
sello, juego y grasa; la marca permanece como atributo.
"""
        ),
        code(
            """
ventas = add_parser_columns(load_sales())
assert set(ventas["nit"].astype(str)) == {NIT}

fecha_max = ventas["fecha"].max().normalize()
fecha_inicio = fecha_max - pd.DateOffset(months=VENTANA_MESES) + pd.Timedelta(days=1)
es_rigido = ventas["nombreproducto"].fillna("").str.upper().eq("RODAMIENTO RIGIDO DE BOLAS")
universo = ventas[ventas["parser_ok"] & es_rigido].copy()
ventana = universo[universo["fecha"].between(fecha_inicio, fecha_max)].copy()

fallos = (
    ventas[es_rigido & ~ventas["parser_ok"]]
    .groupby(["prefijo_1", "parser_error"], dropna=False)
    .agg(volumen_neto=("cantidad", "sum"), lineas=("sales_line_key", "count"))
    .reset_index()
    .sort_values(["volumen_neto", "lineas"], ascending=False)
)

validacion = pd.DataFrame([
    normalize_designation("6204-C-2HRS-L038-C3"),
    normalize_designation("6205-2RSH/C3GJN"),
])[["raw", "llave_canonica", "grasa"]]
display(validacion)

resumen_carga = pd.DataFrame({
    "Indicador": [
        "Líneas totales del cliente",
        "Primera fecha disponible",
        "Última fecha disponible",
        "Líneas elegibles en ventana",
        "Líneas DCC elegibles en ventana",
        "Cantidad neta DCC en ventana",
        "Códigos fuera del parser/universo",
    ],
    "Valor": [
        f"{len(ventas):,}",
        ventas["fecha"].min().date().isoformat(),
        ventas["fecha"].max().date().isoformat(),
        f"{len(ventana):,}",
        f"{ventana['prefijo'].eq('DCC').sum():,}",
        f"{ventana.loc[ventana['prefijo'].eq('DCC'), 'cantidad'].sum():,.0f}",
        f"{len(fallos):,}",
    ],
})
display(resumen_carga)
"""
        ),
        md(
            """
### Códigos no clasificados

Esta tabla es el control de calidad del parser. Incluye exclusiones deliberadas
(`NR`, 64xx y referencias fuera de las series objetivo) para que ninguna línea
desaparezca silenciosamente.
"""
        ),
        code("display(fallos)"),
        md(
            """
## 3. Consumo neto por llave canónica

Cada fila suma SKF, FAG, NTN y cualquier otra marca bajo la misma identidad técnica.
Las cantidades DCC negativas reducen el consumo.
"""
        ),
        code(
            """
consumo = (
    ventana.groupby(
        ["parser_llave_canonica", "parser_tamano", "parser_sello", "parser_juego"],
        dropna=False,
    )["cantidad"]
    .sum()
    .reset_index(name="consumo_12m")
    .rename(columns={
        "parser_llave_canonica": "llave_canonica",
        "parser_tamano": "tamano",
        "parser_sello": "sello",
        "parser_juego": "juego",
    })
)
consumo = consumo[consumo["consumo_12m"] > 0].copy()
consumo["consumo_mensual"] = consumo["consumo_12m"] / 12
display(consumo.sort_values("consumo_12m", ascending=False))
"""
        ),
        md(
            """
## 4. Regla simple de nivel

El nivel crudo equivale al consumo mensual por los meses de cobertura. Solo el nivel
final se redondea hacia arriba a número par.
"""
        ),
        code(
            """
costos = recent_costs(universo)
base = consumo.merge(costos, on="llave_canonica", how="left")
assert base["costo_unitario_reciente"].notna().all(), "Hay referencias sin costo reciente"

base["nivel_crudo"] = base["consumo_mensual"] * MESES_COBERTURA
base["costo_par"] = 2 * base["costo_unitario_reciente"]
base["elegible_por_nivel"] = (
    base["nivel_crudo"].ge(2)
    | (
        base["nivel_crudo"].ge(1)
        & base["nivel_crudo"].lt(2)
        & base["costo_par"].lt(UMBRAL_PAR)
    )
)
base["motivo_nivel"] = np.select(
    [
        base["nivel_crudo"].lt(1),
        base["nivel_crudo"].ge(1) & base["nivel_crudo"].lt(2)
        & base["costo_par"].ge(UMBRAL_PAR),
    ],
    ["ROTACION_BAJA", "COSTO_ALTO"],
    default="",
)
base["nivel_pre_sello"] = np.where(
    base["elegible_por_nivel"], base["nivel_crudo"].map(ceil_even), 0
).astype(int)

display(base[[
    "llave_canonica", "consumo_12m", "consumo_mensual", "nivel_crudo",
    "costo_par", "nivel_pre_sello", "motivo_nivel",
]].sort_values("consumo_12m", ascending=False))
"""
        ),
        md(
            """
## 5. Consolidación 2Z frente a 2RS

La participación se calcula después de sumar todos los juegos de cada sello dentro
del tamaño. Si METAL o CAUCHO alcanza 80%, el otro sello se maneja contra pedido.
Las referencias abiertas se conservan separadas y deben superar por sí mismas la
regla de nivel.
"""
        ),
        code(
            """
sellados = base[base["sello"].isin(["METAL", "CAUCHO"])].copy()
dist_sello = (
    sellados.groupby(["tamano", "sello"])["consumo_12m"]
    .sum().reset_index(name="consumo_sello")
)
dist_sello["consumo_tamano_sellado"] = dist_sello.groupby("tamano")[
    "consumo_sello"
].transform("sum")
dist_sello["participacion"] = (
    dist_sello["consumo_sello"] / dist_sello["consumo_tamano_sellado"]
)
max_share = dist_sello.groupby("tamano")["participacion"].max()
dist_sello["regla_actua"] = dist_sello["tamano"].map(max_share).ge(UMBRAL_SELLO)
dist_sello["sello_seleccionado"] = (
    ~dist_sello["regla_actua"] | dist_sello["participacion"].ge(UMBRAL_SELLO)
)

base = base.merge(
    dist_sello[["tamano", "sello", "participacion", "regla_actua", "sello_seleccionado"]],
    on=["tamano", "sello"], how="left",
)
base["participacion"] = base["participacion"].fillna(1.0)
base["regla_actua"] = base["regla_actua"].fillna(False).astype(bool)
base["sello_seleccionado"] = base["sello_seleccionado"].fillna(True).astype(bool)
base["nivel_lh"] = np.where(
    base["elegible_por_nivel"] & base["sello_seleccionado"],
    base["nivel_pre_sello"], 0
).astype(int)
base["motivo_final"] = base["motivo_nivel"]
base.loc[
    base["elegible_por_nivel"] & ~base["sello_seleccionado"], "motivo_final"
] = "CONSOLIDACION_SELLO"

tamanos_actuados = (
    dist_sello[dist_sello["regla_actua"]]
    .pivot(index="tamano", columns="sello", values="participacion")
    .fillna(0).reset_index()
)
for columna in ["METAL", "CAUCHO"]:
    if columna not in tamanos_actuados:
        tamanos_actuados[columna] = 0.0
display(
    tamanos_actuados.style.format({"METAL": "{:.1%}", "CAUCHO": "{:.1%}"})
)
"""
        ),
        md(
            """
## 6. Comparativo cliente frente a Lugo Hermanos

La tabla incluye la unión completa entre lo solicitado y lo que califica. Los
desacuerdos aparecen primero. La razón está redactada para poder compartir la tabla
sin explicación adicional.
"""
        ),
        code(
            """
lista_cliente = pd.read_csv(StringIO(LISTA_CLIENTE_CSV))
lista_parseada = pd.DataFrame(
    lista_cliente["referencia"].map(normalize_designation).tolist(),
    index=lista_cliente.index,
).add_prefix("parser_")
lista_cliente = pd.concat([lista_cliente, lista_parseada], axis=1)
assert lista_cliente["parser_ok"].all()
cliente = (
    lista_cliente.groupby("parser_llave_canonica")
    .agg(
        sugerido_cliente=("unidades", "sum"),
        referencias_cliente=("referencia", lambda x: "|".join(x)),
    )
    .reset_index()
    .rename(columns={"parser_llave_canonica": "llave_canonica"})
)

base["referencia_skf"] = base["llave_canonica"].map(
    lambda key: skf_dispatch_reference(key, universo)
)
comparativo = base.merge(cliente, on="llave_canonica", how="outer")
comparativo["sugerido_cliente"] = comparativo["sugerido_cliente"].fillna(0).astype(int)
for col in ["consumo_12m", "consumo_mensual", "nivel_lh", "nivel_crudo"]:
    comparativo[col] = comparativo[col].fillna(0)
comparativo["nivel_lh"] = comparativo["nivel_lh"].astype(int)

# Completa referencia y costo para llaves que solo están en la lista del cliente.
comparativo["referencia_skf"] = comparativo["referencia_skf"].fillna(
    comparativo["referencias_cliente"].str.split("|").str[0]
)
comparativo = comparativo.merge(
    costos.rename(columns={"costo_unitario_reciente": "costo_respaldo"})[
        ["llave_canonica", "costo_respaldo"]
    ],
    on="llave_canonica", how="left",
)
comparativo["costo_unitario"] = comparativo["costo_unitario_reciente"].fillna(
    comparativo["costo_respaldo"]
)
comparativo["diferencia"] = (
    comparativo["nivel_lh"] - comparativo["sugerido_cliente"]
)
comparativo["meses_cobertura_sugerido"] = np.where(
    comparativo["consumo_mensual"] > 0,
    comparativo["sugerido_cliente"] / comparativo["consumo_mensual"],
    np.nan,
)
comparativo["valor_costo_lh"] = (
    comparativo["nivel_lh"] * comparativo["costo_unitario"]
)

def estado(row):
    cliente_u, lh_u = row["sugerido_cliente"], row["nivel_lh"]
    if cliente_u > 0 and lh_u == 0:
        return "NO_ENTRA"
    if cliente_u == 0 and lh_u > 0:
        return "AGREGAR"
    if lh_u > cliente_u:
        return "SUBIR"
    if lh_u < cliente_u:
        return "BAJAR"
    return "COINCIDE"

comparativo["estado"] = comparativo.apply(estado, axis=1)

last_movement = universo.groupby("parser_llave_canonica")["fecha"].max()
selected_by_size_seal = (
    base[base["nivel_lh"] > 0]
    .sort_values(["tamano", "nivel_lh"], ascending=[True, False])
)

def razon(row):
    consumo = row["consumo_12m"]
    mensual = row["consumo_mensual"]
    state = row["estado"]
    key = row["llave_canonica"]
    size = key.split(" | ")[0]
    if state == "NO_ENTRA":
        if consumo == 0:
            last = last_movement.get(key, pd.NaT)
            suffix = (
                f"último movimiento: {last:%Y-%m}"
                if pd.notna(last) else "sin movimiento histórico"
            )
            return f"Sin consumo en 12 meses ({suffix})."
        if row.get("motivo_final") == "CONSOLIDACION_SELLO":
            selected = selected_by_size_seal[
                selected_by_size_seal["tamano"].eq(size)
            ].iloc[0]
            share = selected["participacion"]
            return (
                f"El tamaño {size} consume {share:.0%} en "
                f"{'2Z' if selected['sello'] == 'METAL' else '2RS'}. "
                f"Se consolida en {selected['referencia_skf']} "
                f"(nivel {selected['nivel_lh']})."
            )
        if row.get("motivo_final") == "COSTO_ALTO":
            return (
                f"Consumo de {consumo:.0f} und/año pero el par cuesta "
                f"{PESO(row['costo_par'])}. Se maneja contra pedido."
            )
        crudo = row["nivel_crudo"]
        return (
            f"Consumo de {consumo:.0f} und/año ({mensual:.1f}/mes). "
            f"Con {MESES_COBERTURA:g} meses de cobertura da {crudo:.1f} und. "
            "Se maneja contra pedido, entrega 24-48h."
        )
    if state == "AGREGAR":
        other = ventana[
            ventana["parser_llave_canonica"].eq(key) & ventana["sufijo"].ne("SKF")
        ]
        brand = (
            other.groupby("sufijo")["cantidad"].sum().idxmax()
            if not other.empty else "otra marca"
        )
        return (
            f"Consumo de {consumo:.0f} und/año, no estaba en la lista. "
            f"Hoy se surte con {brand}."
        )
    if state == "SUBIR":
        days = (
            row["sugerido_cliente"] / mensual * (365 / 12)
            if mensual > 0 else 0
        )
        return (
            f"Consumo de {consumo:.0f} und/año ({mensual:.1f}/mes). "
            f"Lo sugerido cubre {days:.1f} días."
        )
    if state == "BAJAR":
        return (
            f"Consumo de {consumo:.0f} und/año ({mensual:.1f}/mes). "
            f"Lo sugerido cubre {row['meses_cobertura_sugerido']:.1f} meses."
        )
    return f"Consumo de {consumo:.0f} und/año. Coincide con lo sugerido."

comparativo["razon"] = comparativo.apply(razon, axis=1)
order = {"NO_ENTRA": 0, "BAJAR": 1, "SUBIR": 2, "AGREGAR": 3, "COINCIDE": 4}
comparativo["_orden"] = comparativo["estado"].map(order)
comparativo = comparativo.sort_values(
    ["_orden", "valor_costo_lh"], ascending=[True, False], na_position="last"
)

tabla_principal = comparativo[[
    "referencia_skf", "sugerido_cliente", "nivel_lh", "diferencia",
    "consumo_12m", "consumo_mensual", "meses_cobertura_sugerido",
    "costo_unitario", "valor_costo_lh", "estado", "razon",
]].rename(columns={
    "referencia_skf": "Referencia SKF",
    "sugerido_cliente": "Sugerido cliente",
    "nivel_lh": "Calculado LH",
    "diferencia": "Diferencia",
    "consumo_12m": "Consumo 12m",
    "consumo_mensual": "Consumo mensual",
    "meses_cobertura_sugerido": "Meses cobertura sugerido",
    "costo_unitario": "Costo unitario",
    "valor_costo_lh": "Valor a costo LH",
    "estado": "Estado",
    "razon": "Razón",
})
display(tabla_principal.style.format({
    "Sugerido cliente": "{:,.0f}",
    "Calculado LH": "{:,.0f}",
    "Diferencia": "{:+,.0f}",
    "Consumo 12m": "{:,.1f}",
    "Consumo mensual": "{:,.1f}",
    "Meses cobertura sugerido": "{:,.1f}",
    "Costo unitario": PESO,
    "Valor a costo LH": PESO,
}, na_rep="—"))
"""
        ),
        md(
            """
### Resumen por estado

Las unidades del cliente y de LH permiten separar el efecto de cada desacuerdo; el
capital corresponde exclusivamente al nivel calculado por LH.
"""
        ),
        code(
            """
por_estado = (
    comparativo.groupby("estado", observed=True)
    .agg(
        referencias=("llave_canonica", "size"),
        unidades_cliente=("sugerido_cliente", "sum"),
        unidades_lh=("nivel_lh", "sum"),
        capital_lh=("valor_costo_lh", "sum"),
    )
    .reindex(["NO_ENTRA", "BAJAR", "SUBIR", "AGREGAR", "COINCIDE"])
    .dropna(how="all")
    .reset_index()
)
display(por_estado.style.format({
    "referencias": "{:,.0f}",
    "unidades_cliente": "{:,.0f}",
    "unidades_lh": "{:,.0f}",
    "capital_lh": PESO,
}))
"""
        ),
        md(
            """
## 7. Sensibilidad a los meses de cobertura

La consolidación por sello se mantiene fija; para cada escenario se vuelve a aplicar
la elegibilidad, el umbral del par y el redondeo a pares.
"""
        ),
        code(
            """
def escenario(meses):
    x = base.copy()
    x["crudo"] = x["consumo_mensual"] * meses
    x["entra_nivel"] = (
        x["crudo"].ge(2)
        | (
            x["crudo"].ge(1) & x["crudo"].lt(2)
            & x["costo_par"].lt(UMBRAL_PAR)
        )
    )
    x["nivel"] = np.where(
        x["entra_nivel"] & x["sello_seleccionado"],
        x["crudo"].map(ceil_even), 0
    ).astype(int)
    x["capital"] = x["nivel"] * x["costo_unitario_reciente"]
    return {
        "Meses": meses,
        "Referencias que entran": int(x["nivel"].gt(0).sum()),
        "Unidades": int(x["nivel"].sum()),
        "Capital a costo": x["capital"].sum(),
    }

sensibilidad = pd.DataFrame([escenario(m) for m in [1.5, 2, 2.5, 3, 4]])
display(sensibilidad.style.format({
    "Meses": "{:.1f}",
    "Referencias que entran": "{:,.0f}",
    "Unidades": "{:,.0f}",
    "Capital a costo": PESO,
}))

fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(sensibilidad["Meses"], sensibilidad["Capital a costo"], marker="o")
ax.set_xlabel("Meses de cobertura")
ax.set_ylabel("Capital a costo (COP)")
ax.set_title("Sensibilidad del capital inicial")
ax.grid(axis="y", alpha=0.25)
ax.ticklabel_format(style="plain", axis="y")
plt.show()
"""
        ),
        md(
            """
## 8. Resumen ejecutivo

La propuesta simple se compara con los dos puntos de referencia conocidos. El nivel
estadístico se muestra únicamente como antecedente descartado.
"""
        ),
        code(
            """
resumen = pd.DataFrame([
    {
        "Escenario": "Lista del cliente",
        "Referencias": 59,
        "Unidades": 167,
        "Capital a costo": 9_096_247,
    },
    {
        "Escenario": f"Regla simple ({MESES_COBERTURA:g} meses)",
        "Referencias": int((comparativo["nivel_lh"] > 0).sum()),
        "Unidades": int(comparativo["nivel_lh"].sum()),
        "Capital a costo": comparativo["valor_costo_lh"].sum(),
    },
    {
        "Escenario": "Propuesta estadística descartada",
        "Referencias": 72,
        "Unidades": 449,
        "Capital a costo": 19_464_306,
    },
])
display(resumen.style.format({
    "Referencias": "{:,.0f}",
    "Unidades": "{:,.0f}",
    "Capital a costo": PESO,
}))
"""
        ),
        md(
            """
## Exportación opcional

El notebook es el entregable principal. Cambie `EXPORTAR` a `True` solo si necesita
enviar las tablas fuera del notebook.
"""
        ),
        code(
            """
EXPORTAR = False
if EXPORTAR:
    destino = Path("outputs/sermotor_notebook")
    destino.mkdir(parents=True, exist_ok=True)
    tabla_principal.to_csv(destino / "comparativo.csv", index=False)
    sensibilidad.to_csv(destino / "sensibilidad.csv", index=False)
    resumen.to_csv(destino / "resumen.csv", index=False)
    print(f"Exportado en {destino.resolve()}")
else:
    print("Exportación desactivada.")
"""
        ),
    ]
    return nb


def monthly_notebook():
    levels_path = (
        ROOT
        / "outputs"
        / "sermotor_nivel_inicial"
        / "tabla_a_lista_arranque.csv"
    )
    with levels_path.open(encoding="utf-8", newline="") as source:
        level_rows = list(csv.DictReader(source))
    agreed_levels = {
        row["llave_canonica"]: int(float(row["nivel_inicial"]))
        for row in level_rows
    }
    dispatch_references = {
        row["llave_canonica"]: row["referencia_skf_sugerida"]
        for row in level_rows
    }
    nb = nbf.v4.new_notebook()
    nb["metadata"]["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb["metadata"]["language_info"] = {"name": "python", "version": "3.12"}
    nb["cells"] = [
        md(
            """
# Seguimiento mensual de consignación SERMOTOR

Este notebook recibe uno o varios conteos por referencia y produce la tabla de
decisión mensual. El archivo mínimo contiene:
`referencia, unidades_en_bodega, fecha_conteo`.

Puede añadirse `reposiciones` como cuarta columna. Si se omite, se asume cero y la
salida lo informa explícitamente.
"""
        ),
        code(
            """
from pathlib import Path
import numpy as np
import pandas as pd
from IPython.display import display

from scripts.analyze_sermotor_consignacion import ceil_even, normalize_designation

ARCHIVO_CONTEO = Path("outputs/sermotor_nivel_inicial/plantilla_conteo_ejemplo.csv")
MESES_COBERTURA = 2.5
CONTEOS_PARA_PROMEDIO = 3

# Niveles aprobados al iniciar el acuerdo. Quedan dentro del notebook para que
# este seguimiento solo requiera el CSV de conteo.
NIVELES_ACORDADOS = __AGREED_LEVELS__
REFERENCIAS_DESPACHO = __DISPATCH_REFERENCES__

pd.set_option("display.max_rows", 200)
""".replace("__AGREED_LEVELS__", repr(agreed_levels)).replace(
                "__DISPATCH_REFERENCES__", repr(dispatch_references)
            )
        ),
        md(
            """
## Carga, validación y cálculo

El consumo del periodo es `nivel acordado − unidades contadas + reposiciones`.
El acumulado usa hasta los últimos tres conteos disponibles. Después de tres conteos
sin consumo se recomienda retirar la referencia.
"""
        ),
        code(
            """
conteos = pd.read_csv(ARCHIVO_CONTEO)
obligatorias = {"referencia", "unidades_en_bodega", "fecha_conteo"}
faltantes = obligatorias - set(conteos.columns)
if faltantes:
    raise ValueError(f"Faltan columnas: {sorted(faltantes)}")

if "reposiciones" not in conteos:
    conteos["reposiciones"] = 0
    tratamiento_reposiciones = "ASUMIDAS_CERO"
else:
    tratamiento_reposiciones = "INFORMADAS_EN_ARCHIVO"

parsed = pd.DataFrame(
    conteos["referencia"].map(normalize_designation).tolist(),
    index=conteos.index,
).add_prefix("parser_")
conteos = pd.concat([conteos, parsed], axis=1)
if not conteos["parser_ok"].all():
    display(conteos.loc[~conteos["parser_ok"], ["referencia", "parser_error"]])
    raise ValueError("Hay referencias que el parser no reconoce.")

conteos["fecha_conteo"] = pd.to_datetime(conteos["fecha_conteo"], errors="raise")
conteos["unidades_en_bodega"] = pd.to_numeric(
    conteos["unidades_en_bodega"], errors="raise"
)
conteos["reposiciones"] = pd.to_numeric(conteos["reposiciones"], errors="raise")
if (conteos[["unidades_en_bodega", "reposiciones"]] < 0).any().any():
    raise ValueError("Conteos y reposiciones deben ser no negativos.")

niveles = pd.DataFrame({
    "llave_canonica": list(NIVELES_ACORDADOS),
    "nivel_acordado": list(NIVELES_ACORDADOS.values()),
})
niveles["referencia_skf_sugerida"] = niveles["llave_canonica"].map(
    REFERENCIAS_DESPACHO
)
conteos = conteos.merge(
    niveles,
    left_on="parser_llave_canonica",
    right_on="llave_canonica",
    how="left",
)
if conteos["nivel_acordado"].isna().any():
    display(conteos.loc[
        conteos["nivel_acordado"].isna(),
        ["referencia", "parser_llave_canonica"],
    ])
    raise ValueError("Hay referencias sin nivel acordado.")

conteos = conteos.sort_values(["llave_canonica", "fecha_conteo"])
conteos["consumo_periodo"] = (
    conteos["nivel_acordado"]
    - conteos["unidades_en_bodega"]
    + conteos["reposiciones"]
)
if conteos["consumo_periodo"].lt(0).any():
    raise ValueError("Hay consumo negativo; revise conteos o reposiciones.")

grupo = conteos.groupby("llave_canonica", group_keys=False)
conteos["numero_conteo"] = grupo.cumcount() + 1
conteos["consumo_ultimos_3"] = grupo["consumo_periodo"].transform(
    lambda s: s.rolling(CONTEOS_PARA_PROMEDIO, min_periods=1).sum()
)
conteos["consumo_mensual_promedio"] = (
    conteos["consumo_ultimos_3"]
    / conteos["numero_conteo"].clip(upper=CONTEOS_PARA_PROMEDIO)
)
conteos["meses_cobertura"] = np.where(
    conteos["consumo_mensual_promedio"] > 0,
    conteos["nivel_acordado"] / conteos["consumo_mensual_promedio"],
    np.nan,
)
conteos["nivel_recalculado"] = (
    conteos["consumo_mensual_promedio"] * MESES_COBERTURA
).map(ceil_even)

def ajuste(row):
    if row["numero_conteo"] >= 3 and row["consumo_ultimos_3"] == 0:
        return "RETIRAR"
    if row["nivel_recalculado"] > row["nivel_acordado"]:
        return "SUBIR"
    if row["nivel_recalculado"] < row["nivel_acordado"]:
        return "BAJAR"
    return "MANTENER"

conteos["ajuste_sugerido"] = conteos.apply(ajuste, axis=1)
ultimo = conteos.groupby("llave_canonica", as_index=False).tail(1).copy()
reporte = ultimo[[
    "referencia_skf_sugerida", "nivel_acordado", "unidades_en_bodega",
    "consumo_periodo", "consumo_ultimos_3", "meses_cobertura",
    "ajuste_sugerido",
]].rename(columns={
    "referencia_skf_sugerida": "Referencia",
    "nivel_acordado": "Nivel acordado",
    "unidades_en_bodega": "Unidades contadas",
    "consumo_periodo": "Consumo del periodo",
    "consumo_ultimos_3": "Consumo mensual acumulado (últimos 3 conteos)",
    "meses_cobertura": "Meses de cobertura del nivel actual",
    "ajuste_sugerido": "Ajuste sugerido",
})
print(f"Tratamiento de reposiciones: {tratamiento_reposiciones}")
display(reporte.style.format({
    "Nivel acordado": "{:,.0f}",
    "Unidades contadas": "{:,.0f}",
    "Consumo del periodo": "{:,.0f}",
    "Consumo mensual acumulado (últimos 3 conteos)": "{:,.1f}",
    "Meses de cobertura del nivel actual": "{:,.1f}",
}, na_rep="—"))
"""
        ),
    ]
    return nb


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))
    execute_and_save(initial_notebook(), NOTEBOOKS / "consignacion_sermotor.ipynb")
    execute_and_save(
        monthly_notebook(), NOTEBOOKS / "seguimiento_mensual_sermotor.ipynb"
    )
    print(f"Generados y ejecutados en {NOTEBOOKS}")


if __name__ == "__main__":
    main()
