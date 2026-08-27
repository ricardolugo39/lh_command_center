class CommercialApprovalEventPublisher:
    """No-op integration hook for future notification adapters."""

    @staticmethod
    def publish(event_name: str, payload: dict) -> None:
        return None
