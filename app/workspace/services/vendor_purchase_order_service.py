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
    ELIGIBLE_QUOTE_STATUSES = {"sent_sales_rep", "won"}

    @staticmethod
    def latest(quote_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            direct = connection.execute(
                """SELECT d.*,d.vendor_name brand,1 is_direct
                FROM direct_vendor_purchase_order_drafts d
                WHERE d.quote_id=? ORDER BY d.id DESC LIMIT 1""",
                (quote_id,),
            ).fetchone()
            row = connection.execute(
                """SELECT d.*,vr.brand FROM vendor_purchase_order_drafts d
                JOIN rfq_vendor_requests vr ON vr.id=d.vendor_request_id
                WHERE d.quote_id=? ORDER BY d.id DESC LIMIT 1""",
                (quote_id,),
            ).fetchone()
        if direct:
            return dict(direct)
        return {**dict(row), "is_direct": 0} if row else None

    @staticmethod
    def _content(vendor_name: str, reference: str) -> tuple[str, str, str]:
        subject = f"Purchase Order – Quote {reference}"
        body_text = (
            f"Hi {vendor_name} team,\n\n"
            "Please find attached our purchase order for the items included in "
            "your quotation.\n\n"
            "Your original quotation is also attached for reference.\n\n"
            "Please confirm receipt of the purchase order and provide the expected "
            "ship or delivery date.\n\n"
            "Best regards,\nRicardo Lugo"
        )
        return subject, body_text, (
            "<p>" + html.escape(body_text).replace("\n", "<br>") + "</p>"
        )

    @classmethod
    def create_direct_draft(
        cls, quote_id: int, recipient_email: str, vendor_name: str,
        attachment_id: int, actor: int,
    ) -> dict[str, Any]:
        quote = QuoteManagementRepository.get(quote_id)
        if not quote or quote.get("originating_rfq_id"):
            raise ValueError("Esta acción corresponde a una cotización directa.")
        if quote.get("quote_status") not in cls.ELIGIBLE_QUOTE_STATUSES:
            raise ValueError("Primero envíe la cotización al asesor comercial.")
        pending = cls.latest(quote_id)
        if pending and pending.get("status") == "draft":
            raise ValueError("Ya existe un borrador de PO pendiente en el correo.")
        recipient = parseaddr(recipient_email or "")[1].casefold()
        if not recipient or "@" not in recipient:
            raise ValueError("Ingrese un correo válido del proveedor.")
        vendor = str(vendor_name or "Vendor").strip() or "Vendor"
        attachment = next(
            (
                item for item in QuoteManagementRepository.attachments(quote_id)
                if item["id"] == attachment_id
            ),
            None,
        )
        if not attachment or not Path(attachment["stored_filename"]).is_file():
            raise ValueError("No se encontró el PDF de cotización del proveedor.")
        if str(attachment.get("mime_type") or "").casefold() != "application/pdf":
            raise ValueError("La cotización del proveedor debe ser un archivo PDF.")
        reference = f"{quote['prefix']}-{quote['quote_number']}"
        subject, body_text, body_html = cls._content(vendor, reference)
        file_payload = [{
            "path": attachment["stored_filename"],
            "filename": attachment["original_filename"],
            "mime_type": attachment.get("mime_type"),
        }]
        try:
            result = current_app.extensions["email_provider"].create_message_draft(
                sender=cls.SENDER, recipients=[recipient], cc=[], subject=subject,
                body_text=body_text, body_html=body_html,
                attachments=file_payload,
            )
        except Exception as error:
            current_app.logger.exception("No se pudo crear el borrador directo de PO")
            raise ValueError(
                "La cotización se conservó, pero no se pudo crear el borrador."
            ) from error
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO direct_vendor_purchase_order_drafts(
                quote_id,recipient_email,vendor_name,subject,body_text,attachment_id,
                provider_draft_id,provider_message_id,provider_thread_id,
                prepared_by_user_id,email_provider) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    quote_id, recipient, vendor, subject, body_text, attachment_id,
                    result["draft_id"], result.get("message_id"),
                    result["thread_id"], actor,
                    current_app.config.get("EMAIL_PROVIDER", "gmail"),
                ),
            )
        return {"id": int(cursor.lastrowid), **result}

    @classmethod
    def create_draft(
        cls, quote_id: int, vendor_request_id: int, actor: int,
    ) -> dict[str, Any]:
        quote = QuoteManagementRepository.get(quote_id)
        if not quote or not quote.get("originating_rfq_id"):
            raise ValueError("La cotización no tiene una RFQ de origen.")
        if quote.get("quote_status") not in cls.ELIGIBLE_QUOTE_STATUSES:
            raise ValueError(
                "Primero envíe la cotización al asesor comercial y márquela "
                "como ganada cuando reciba la orden del cliente."
            )
        pending = cls.latest(quote_id)
        if pending and pending.get("status") == "draft":
            raise ValueError("Ya existe un borrador de PO pendiente en el correo.")
        rfq_id = int(quote["originating_rfq_id"])
        vendor_request = RFQVendorRequestRepository.get_for_rfq(
            rfq_id, vendor_request_id
        )
        if not vendor_request or not vendor_request.get("provider_thread_id"):
            raise ValueError("No se encontró la conversación del proveedor.")
        if vendor_request.get("email_provider", "gmail") != current_app.config.get(
            "EMAIL_PROVIDER", "gmail"
        ):
            raise ValueError(
                "La conversación original pertenece a Gmail y se conserva como "
                "historial; debe iniciar un correo nuevo en Microsoft 365."
            )
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
            result = current_app.extensions["email_provider"].create_reply_draft(
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
                "La cotización se conservó, pero no se pudo crear el borrador."
            ) from error
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO vendor_purchase_order_drafts(
                quote_id,rfq_id,vendor_request_id,recipient_email,subject,body_text,
                provider_draft_id,provider_message_id,provider_thread_id,
                prepared_by_user_id,email_provider) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    quote_id, rfq_id, vendor_request_id, recipient, subject,
                    body_text, result["draft_id"], result.get("message_id"),
                    result["thread_id"], actor,
                    current_app.config.get("EMAIL_PROVIDER", "gmail"),
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
            table = (
                "direct_vendor_purchase_order_drafts"
                if draft.get("is_direct") else "vendor_purchase_order_drafts"
            )
            connection.execute(
                f"""UPDATE {table} SET status='sent',
                confirmed_by_user_id=?,confirmed_at=CURRENT_TIMESTAMP WHERE id=?""",
                (actor, draft["id"]),
            )
        QuoteManagementRepository.record_won_from_purchase_order(quote_id, actor)
        if draft.get("is_direct"):
            return
        rfq = RFQRepository.get(draft["rfq_id"])
        RFQRepository.update_status(
            draft["rfq_id"], "won", "closed", (rfq or {}).get("opportunity_id")
        )
        RFQRepository.add_history(
            draft["rfq_id"], (rfq or {}).get("workflow_status"), "closed", actor,
            "PO enviada al proveedor; RFQ archivada",
        )
