from app.workspace.repositories.rfq_repository import RFQRepository
from app.workspace.repositories.rfq_vendor_request_repository import (
    RFQVendorRequestRepository,
)
from app.workspace.services.quote_weight_research_service import (
    QuoteWeightResearchService,
)


class RFQWeightResearchService:
    @staticmethod
    def search(rfq_id: int, item_id: int, actor: int) -> int:
        item = RFQRepository.get_item(rfq_id, item_id)
        if not item:
            raise ValueError("La línea no pertenece a esta RFQ.")
        messages = RFQVendorRequestRepository.list_messages(rfq_id)
        context = "\n\n".join(
            f"Asunto: {message.get('subject') or ''}\n"
            f"Mensaje: {message.get('body_text') or ''}"
            for message in messages
            if message.get("direction") == "incoming"
            and str(message.get("brand") or "").casefold()
            == str(item.get("brand") or "").casefold()
        )
        result = QuoteWeightResearchService.research_product(
            item["brand"], item["reference"], context
        )
        return RFQRepository.add_weight_research(item_id, result, actor)

    @staticmethod
    def accept(rfq_id: int, item_id: int, research_id: int, actor: int) -> None:
        RFQRepository.accept_weight_research(
            rfq_id, item_id, research_id, actor
        )
