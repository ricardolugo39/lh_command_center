import re


def normalize_product_reference(value) -> str:
    """Canonical comparison key shared by analytics and SQL read models."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def sql_normalize_product_reference(expression: str) -> str:
    # SQLite has no built-in regex replace; cover the separators accepted by
    # the importer while keeping the expression usable inside set queries.
    return (
        "UPPER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE("
        f"TRIM({expression}),' ',''),'-',''),'/',''),'.',''),',',''),'_',''))"
    )
