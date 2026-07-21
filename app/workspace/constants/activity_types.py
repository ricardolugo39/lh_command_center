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

    @classmethod
    def label(cls, activity_type: str) -> str:
        return cls.LABELS.get(
            activity_type,
            activity_type,
        )

    @classmethod
    def is_manual_type(cls, activity_type: str) -> bool:
        return activity_type in cls.MANUAL_TYPES