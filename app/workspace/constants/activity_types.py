class ActivityType:
    PROJECT_CREATED = "project_created"
    STATUS_CHANGED = "status_changed"
    BLOCKER_CHANGED = "blocker_changed"
    FOLLOWUP_CREATED = "followup_created"
    FOLLOWUP_COMPLETED = "followup_completed"
    FOLLOWUP_RESCHEDULED = "followup_rescheduled"
    PROJECT_UPDATED = "project_updated"
    OPPORTUNITY_CLOSED = "opportunity_closed"
    CANCELLED = "cancelled"
    APPROVAL_CREATED = "commercial_approval_created"
    APPROVAL_SUBMITTED = "commercial_approval_submitted"
    APPROVAL_APPROVED = "commercial_approval_approved"
    APPROVAL_RETURNED = "commercial_approval_returned"
    APPROVAL_REJECTED = "commercial_approval_rejected"
    APPROVAL_CANCELLED = "commercial_approval_cancelled"

    CALL = "call"
    VISIT = "visit"
    MEETING = "meeting"
    EMAIL = "email"
    NOTE = "note"

    LABELS = {
        PROJECT_CREATED: "Proyecto creado",
        STATUS_CHANGED: "Estado actualizado",
        BLOCKER_CHANGED: "Bloqueo actualizado",
        FOLLOWUP_CREATED: "Follow-up programado",
        FOLLOWUP_COMPLETED: "Follow-up completado",
        FOLLOWUP_RESCHEDULED: "Follow-up reprogramado",
        OPPORTUNITY_CLOSED: "Oportunidad cerrada",
        CANCELLED: "Cancelada",
        APPROVAL_CREATED: "Solicitud comercial creada",
        APPROVAL_SUBMITTED: "Aprobación comercial enviada",
        APPROVAL_APPROVED: "Descuento comercial aprobado",
        APPROVAL_RETURNED: "Aprobación comercial devuelta",
        APPROVAL_REJECTED: "Aprobación comercial rechazada",
        APPROVAL_CANCELLED: "Solicitud de aprobación cancelada",
        CALL: "Llamada",
        VISIT: "Visita",
        MEETING: "Reunión",
        EMAIL: "Email",
        NOTE: "Nota",
    }

    MANUAL_TYPES = {
        CALL,
        VISIT,
        MEETING,
        EMAIL,
        NOTE,
    }

    COMMERCIAL_APPROVAL_TYPES = {
        APPROVAL_CREATED, APPROVAL_SUBMITTED, APPROVAL_APPROVED,
        APPROVAL_RETURNED, APPROVAL_REJECTED, APPROVAL_CANCELLED,
    }

    @classmethod
    def label(cls, activity_type: str) -> str:
        return cls.LABELS.get(
            activity_type,
            activity_type,
        )

    @classmethod
    def is_manual_type(cls, activity_type: str) -> bool:
        return activity_type in cls.MANUAL_TYPES
