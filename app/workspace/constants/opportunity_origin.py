"""Controlled, immutable origins for commercial Opportunities."""


class OpportunityOrigin:
    MANUAL = "manual"
    CRM = "crm"
    QUOTE = "quote"
    VISIT = "visit"
    RFQ = "rfq"

    ALL = frozenset({MANUAL, CRM, QUOTE, VISIT, RFQ})

    LABELS = {
        MANUAL: "Manual",
        CRM: "CRM",
        QUOTE: "Cotización",
        VISIT: "Visita",
        RFQ: "RFQ",
    }

    @classmethod
    def normalize(cls, value: str | None) -> str:
        normalized = str(value or cls.MANUAL).strip().lower()
        if normalized not in cls.ALL:
            raise ValueError(f"Invalid Opportunity origin: {normalized}")
        return normalized

    @classmethod
    def label(cls, value: str | None) -> str:
        return cls.LABELS.get(cls.normalize(value), "Manual")
