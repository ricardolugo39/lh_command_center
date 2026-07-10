class ProjectStatus:

    PROSPECT = "prospect"
    QUOTING = "quoting"
    WAITING_CUSTOMER = "waiting_customer"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"

    LABELS = {
        PROSPECT: "Prospecto",
        QUOTING: "Cotizando",
        WAITING_CUSTOMER: "Esperando cliente",
        NEGOTIATION: "Negociación",
        WON: "Ganado",
        LOST: "Perdido",
    }

    @classmethod
    def label(cls, status: str) -> str:
        return cls.LABELS.get(status, status)