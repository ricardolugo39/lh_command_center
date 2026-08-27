class CustomerPortfolioStatusPolicy:
    """Temporary deterministic commercial status; not an Account Health score."""

    INACTIVE_SQL = "(last_activity = '' OR date(last_activity) < date('now', '-60 days'))"
    RISK_SQL = "(last_purchase_date IS NULL OR date(last_purchase_date) < date('now', '-90 days') OR (revenue_ytd = 0 AND revenue_ly > 0))"
    STATE_SORT_SQL = "CASE WHEN last_purchase_date IS NULL OR date(last_purchase_date) < date('now','-90 days') OR (revenue_ytd = 0 AND revenue_ly > 0) THEN 3 WHEN date(last_purchase_date) < date('now','-60 days') OR last_activity = '' OR date(last_activity) < date('now','-60 days') THEN 2 ELSE 1 END"

    @staticmethod
    def classify(*, current: float, previous: float,
                 purchase_days: int | None, activity_days: int | None,
                 open_opportunities: int, active_agreement: bool,
                 has_pending_action: bool):
        if purchase_days is None or purchase_days > 90 or (current == 0 and previous > 0):
            return {"label": "En riesgo", "tone": "critical"}
        growth = (current - previous) / previous * 100 if previous else None
        if (purchase_days > 60 or activity_days is None or activity_days > 60
                or (growth is not None and growth < -20) or has_pending_action):
            return {"label": "Atención", "tone": "warning"}
        if (current > 0 and growth is not None and growth >= 0
                and purchase_days <= 30 and activity_days is not None
                and activity_days <= 30
                and (open_opportunities > 0 or active_agreement)):
            return {"label": "Excelente", "tone": "positive"}
        return {"label": "Buena", "tone": "neutral"}
