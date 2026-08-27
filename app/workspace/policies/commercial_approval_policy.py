class CommercialApprovalPolicy:
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PENDING = "pending_approval"
    RETURNED = "returned"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    LABELS = {
        DRAFT: "Borrador", SUBMITTED: "Enviada", PENDING: "Pendiente de aprobación",
        RETURNED: "Devuelta", APPROVED: "Aprobada", REJECTED: "Rechazada",
        CANCELLED: "Cancelada", EXPIRED: "Vencida",
    }
    TRANSITIONS = {
        DRAFT: {SUBMITTED, CANCELLED},
        SUBMITTED: {PENDING, CANCELLED},
        PENDING: {APPROVED, REJECTED, RETURNED, CANCELLED, EXPIRED},
        RETURNED: {SUBMITTED, CANCELLED},
        APPROVED: {EXPIRED},
        REJECTED: set(), CANCELLED: set(), EXPIRED: set(),
    }
    DECISION_STATUS = {
        "approved": APPROVED, "rejected": REJECTED, "returned": RETURNED,
    }

    @classmethod
    def require_transition(cls, current: str, target: str) -> None:
        if target not in cls.TRANSITIONS.get(current, set()):
            raise ValueError(
                f"Transición de aprobación no permitida: "
                f"{cls.LABELS.get(current, current)} → {cls.LABELS.get(target, target)}."
            )

    @classmethod
    def require_editable(cls, status: str) -> None:
        if status not in {cls.DRAFT, cls.RETURNED}:
            raise ValueError("Solo las solicitudes en borrador o devueltas pueden editarse.")

    @staticmethod
    def require_approver(role: str) -> None:
        if role != "approver":
            raise PermissionError("No tiene autorización para decidir solicitudes comerciales.")
