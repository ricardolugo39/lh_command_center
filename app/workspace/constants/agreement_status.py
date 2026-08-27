STATUS_LABELS = {
    "draft": "Borrador",
    "active": "Activo",
    "renewal": "En renovación",
    "expired": "Vencido",
    "cancelled": "Cancelado",
    "closed": "Cerrado",
}


def get_status_label(status: str | None) -> str:
    return STATUS_LABELS.get(status, status or "Sin información")
