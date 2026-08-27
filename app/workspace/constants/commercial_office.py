"""Canonical commercial-office assignment derived from the ERP seller."""

import unicodedata

CALI_SALES_REPRESENTATIVES = frozenset({
    "ALMACEN CALI -UNO-",
    "DIANA MARIA VELASQUEZ C",
    "FABIO NELSON VALENCIA",
    "JAIRO DAVID VERA",
    "JEISMAN HOLGUIN",
    "JOSE TRINIDAD BELTRAN CARVAJAL",
    "NUBIA ANDREA JIMENEZ",
    "RICARDO LUGO",
    "WHATSAPP CALI",
    "YEISSON ANDRES RENTERIA MOSQUERA",
})

OFFICES = ("Bogotá", "Cali")

SALES_REP_ALIASES = {
    "ANDREA JIMENEZ": "NUBIA ANDREA JIMENEZ",
    "FABIO VALENCIA": "FABIO NELSON VALENCIA",
    "JAIRO VERA": "JAIRO DAVID VERA",
    "JEISMAN HOLGUIN": "JEISMAN HOLGUIN",
    "JOSE BELTRAN": "JOSE TRINIDAD BELTRAN CARVAJAL",
    "YEISSON RENTERIA": "YEISSON ANDRES RENTERIA MOSQUERA",
}


def normalize_sales_rep(value: str | None) -> str:
    text = " ".join(str(value or "").strip().upper().split())
    return "".join(
        character for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )


def canonical_sales_rep(value: str | None) -> str | None:
    normalized = normalize_sales_rep(value)
    if not normalized:
        return None
    return SALES_REP_ALIASES.get(normalized, normalized)


def office_for_sales_rep(value: str | None) -> str:
    return "Cali" if canonical_sales_rep(value) in CALI_SALES_REPRESENTATIVES else "Bogotá"


def sql_office_case(column: str) -> str:
    values = ",".join("'" + value.replace("'", "''") + "'" for value in sorted(CALI_SALES_REPRESENTATIVES))
    return (
        f"CASE WHEN UPPER(TRIM(COALESCE({column},''))) IN ({values}) "
        "THEN 'Cali' ELSE 'Bogotá' END"
    )
