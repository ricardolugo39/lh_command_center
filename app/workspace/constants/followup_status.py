class FollowupStatus:
    PENDING = "pending"
    COMPLETED = "completed"

    LABELS = {
        PENDING: "Pendiente",
        COMPLETED: "Completado",
    }

    @classmethod
    def label(cls, status: str) -> str:
        return cls.LABELS.get(status, status)