"""
Estados y reglas del ciclo de vida de las oportunidades comerciales.
"""

PROSPECT = "prospect"
QUOTING = "quoting"
WAITING_CUSTOMER = "waiting_customer"
NEGOTIATION = "negotiation"

WON = "won"
LOST = "lost"
CANCELLED = "cancelled"


STATUS_LABELS = {
    PROSPECT: "Prospecto",
    QUOTING: "Cotización",
    WAITING_CUSTOMER: "Esperando cliente",
    NEGOTIATION: "Negociación",
    WON: "Ganada",
    LOST: "Perdida",
    CANCELLED: "Cancelada",
}


OPEN_STATUSES = frozenset(
    {
        PROSPECT,
        QUOTING,
        WAITING_CUSTOMER,
        NEGOTIATION,
    }
)


CLOSED_STATUSES = frozenset(
    {
        WON,
        LOST,
        CANCELLED,
    }
)


ALL_STATUSES = frozenset(
    OPEN_STATUSES | CLOSED_STATUSES
)

PIPELINE_STATUS_ORDER = (
    PROSPECT,
    QUOTING,
    WAITING_CUSTOMER,
    NEGOTIATION,
    WON,
    LOST,
)


def is_open(status: str | None) -> bool:
    return status in OPEN_STATUSES


def is_closed(status: str | None) -> bool:
    return status in CLOSED_STATUSES


def is_valid(status: str | None) -> bool:
    return status in ALL_STATUSES


def get_status_label(status: str | None) -> str:
    if not status:
        return "Sin estado"

    return STATUS_LABELS.get(
        status,
        status.replace("_", " ").capitalize(),
    )


class ProjectStatus:
    """Backward-compatible namespace for opportunity statuses."""

    PROSPECT = PROSPECT
    QUOTING = QUOTING
    WAITING_CUSTOMER = WAITING_CUSTOMER
    NEGOTIATION = NEGOTIATION
    WON = WON
    LOST = LOST
    CANCELLED = CANCELLED
    LABELS = STATUS_LABELS

    @classmethod
    def label(cls, status: str) -> str:
        return get_status_label(status)
