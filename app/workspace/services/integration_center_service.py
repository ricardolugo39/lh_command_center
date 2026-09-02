from typing import Any

from app.workspace.services.commercial_visit_service import (
    CommercialVisitService,
)
from app.workspace.services.erp_import_service import ERPImportService
from app.workspace.connectors.gmail_provider import GmailProvider


class IntegrationCenterService:
    """Compose operational integration status without duplicating connectors."""

    @classmethod
    def get_page(cls) -> dict[str, Any]:
        history = ERPImportService.history()
        latest = ERPImportService.detail(history[0]["id"]) if history else None
        return {
            "erp": {
                "latest": latest,
                "history": history[:5],
                "execution_count": len(history),
            },
            "google_visits": CommercialVisitService.get_integration_status(),
            "gmail": {"ready": GmailProvider.configured()},
        }
