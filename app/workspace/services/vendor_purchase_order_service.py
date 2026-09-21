import html
import json
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from flask import current_app

from app.database.transaction import connection_scope, transactional
from app.workspace.repositories.quote_management_repository import (
    QuoteManagementRepository,
)
from app.workspace.repositories.rfq_repository import RFQRepository
from app.workspace.repositories.rfq_vendor_request_repository import (
    RFQVendorRequestRepository,
)


class VendorPurchaseOrderService:
    SENDER = "ricardo.lugo@lugohermanos.com"

    @staticmethod
    def latest(quote_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT d.*,vr.brand FROM vendor_purchase_order_drafts d
                JOIN rfq_vendor_requests vr ON vr.id=d.vendor_request_id
                WHERE d.quote_id=? ORDER BY d.id DESC LIMIT 1""",
                (quote_id,),
            ).fetchone()
        return dict(row) if row else None

    @classmethod
    def create_draft(
        cls, quote_id: int, vendor_request_id: int, actor: int,
    ) -> dict[str, Any]:
        quote = QuoteManagementRepository.get(quote_id)
        if not quote or not quote.get("originating_rfq_id"):
            raise ValueError("La cotización no tiene una RFQ de origen.")
        if quote.get("quote_status") != "sent_sales_rep":
            raise ValueError("Primero envíe la cotización al asesor comercial.")
        pending = cls.latest(quote_id)
        if pending and pending.get("status") == "draft":
            raise ValueError("Ya existe un borrador de PO pendiente en Gmail.")
        rfq_id = int(quote["originating_rfq_id"])
        vendor_request = RFQVendorRequestRepository.get_for_rfq(
            rfq_id, vendor_request_id
        )
        if not vendor_request or not vendor_request.get("provider_thread_id"):
            raise ValueError("No se encontró la conversación del proveedor.")
        incoming = RFQVendorRequestRepository.latest_incoming(vendor_request_id)
        if not incoming:
            raise ValueError("El proveedor todavía no ha respondido esta RFQ.")
        recipient = parseaddr(incoming.get("sender_email") or "")[1].casefold()
        if not recipient or "@" not in recipient:
            raise ValueError("La respuesta del proveedor no tiene un correo válido.")
        files = []
        for attachment in RFQVendorRequestRepository.list_request_attachments(
            vendor_request_id
        ):
            path = Path(attachment["stored_filename"])
            if path.is_file():
                files.append({
                    "path": str(path),
                    "filename": attachment["original_filename"],
                    "mime_type": attachment.get("mime_type"),
                })
        if not files:
            raise ValueError("No se encontró la cotización adjunta del proveedor.")
        rfq = RFQRepository.get(rfq_id)
        number = (rfq or {}).get("prequotation_number") or (rfq or {}).get(
            "rfq_number"
        )
        brand = str(vendor_request.get("brand") or "Vendor").strip()
        subject = f"Purchase Order – RFQ {number}"
        body_text = (
            f"Hi {brand} team,\n\n"
            "Please find attached our purchase order for the items included in "
            "your quotation.\n\n"
            "Your original quotation is also attached for reference.\n\n"
            "Please confirm receipt of the purchase order and provide the expected "
            "ship or delivery date.\n\n"
            "Best regards,\nRicardo Lugo"
        )
        body_html = "<p>" + html.escape(body_text).replace("\n", "<br>") + "</p>"
        try:
            result = current_app.extensions["gmail_provider"].create_reply_draft(
                thread_id=vendor_request["provider_thread_id"],
                sender=cls.SENDER,
                recipients=[recipient],
                cc=json.loads(vendor_request.get("cc_json") or "[]"),
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                attachments=files,
            )
        except Exception as error:
            current_app.logger.exception("No se pudo crear el borrador de PO")
            raise ValueError(
                "La cotización se conservó, pero Gmail no pudo crear el borrador."
            ) from error
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO vendor_purchase_order_drafts(
                quote_id,rfq_id,vendor_request_id,recipient_email,subject,body_text,
                provider_draft_id,provider_message_id,provider_thread_id,
                prepared_by_user_id) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    quote_id, rfq_id, vendor_request_id, recipient, subject,
                    body_text, result["draft_id"], result.get("message_id"),
                    result["thread_id"], actor,
                ),
            )
        return {"id": int(cursor.lastrowid), **result}

    @classmethod
    @transactional
    def confirm_sent(cls, quote_id: int, actor: int) -> None:
        draft = cls.latest(quote_id)
        if not draft or draft.get("status") != "draft":
            raise ValueError("No hay un borrador de PO pendiente por confirmar.")
        with connection_scope() as connection:
            connection.execute(
                """UPDATE vendor_purchase_order_drafts SET status='sent',
                confirmed_by_user_id=?,confirmed_at=CURRENT_TIMESTAMP WHERE id=?""",
                (actor, draft["id"]),
            )
        QuoteManagementRepository.record_won_from_purchase_order(quote_id, actor)
        rfq = RFQRepository.get(draft["rfq_id"])
        RFQRepository.update_status(
            draft["rfq_id"], "won", "closed", (rfq or {}).get("opportunity_id")
        )
        RFQRepository.add_history(
            draft["rfq_id"], (rfq or {}).get("workflow_status"), "closed", actor,
            "PO enviada al proveedor; RFQ archivada",
        )
