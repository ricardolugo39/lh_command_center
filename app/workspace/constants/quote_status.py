OPEN_QUOTE_STATUSES = frozenset(
    {"abierto", "open", "pending", "pendiente"}
)
OPEN_QUOTE_STATUSES_SQL = ",".join(
    f"'{status}'" for status in sorted(OPEN_QUOTE_STATUSES)
)


def is_open_quote_status(status: str | None) -> bool:
    return str(status or "").strip().casefold() in OPEN_QUOTE_STATUSES
