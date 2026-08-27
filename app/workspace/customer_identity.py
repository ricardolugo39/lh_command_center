from typing import Any


def normalize_nit(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "".join(
        character for character in str(value).strip().upper()
        if character.isalnum()
    )


def normalize_site_text(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def customer_site_key(row: dict[str, Any]) -> str:
    return "|".join((
        normalize_nit(row.get("nit")),
        normalize_site_text(row.get("ciudad")),
        normalize_site_text(row.get("direccion1")),
    ))
