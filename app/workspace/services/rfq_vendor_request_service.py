import html
import json
from collections import defaultdict
from hashlib import sha256

from flask import current_app
from werkzeug.utils import secure_filename

from app.database.transaction import connection_scope, transactional
from app.storage import upload_path
from app.workspace.repositories.rfq_repository import RFQRepository
from app.workspace.repositories.rfq_vendor_request_repository import (
    RFQVendorRequestRepository,
)
from app.workspace.services.rfq_service import RFQService


class RFQVendorRequestService:
    TEST_RECIPIENT = "ricardo.lugo@lugohermanos.com"

    @staticmethod
    def _message(
        number: str, items: list[dict], additional_text: str | None = None,
    ) -> tuple[str, str]:
        rows = "".join(
            "<tr>" + "".join(
                f"<td style='padding:6px;border:1px solid #ddd'>{html.escape(str(value or ''))}</td>"
                for value in (
                    item.get("reference"), item.get("quantity"),
                    item.get("notes"),
                )
            ) + "</tr>" for item in items
        )
        extra_html = (
            f"<p>{html.escape(additional_text).replace(chr(10), '<br>')}</p>"
            if additional_text else ""
        )
        body_html = (
            "<p>Hello,</p>"
            "<p>We are requesting pricing and lead time for the following product(s):</p>"
            f"{extra_html}"
            "<p>Please also provide availability and quotation validity. "
            f"Please keep <strong>{html.escape(number)}</strong> in the subject.</p>"
            "<table style='border-collapse:collapse'><thead><tr><th>Product</th>"
            "<th>Quantity</th><th>Comments</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            "<p>Thank you,<br>Ricardo Lugo</p>"
        )
        body_text = "\n".join(
            [
                "Hello,",
                "",
                "We are requesting pricing and lead time for the following product(s):",
                *( ["", additional_text] if additional_text else [] ),
                "",
                "Please also provide availability and quotation validity. "
                f"Please keep {number} in the subject.",
            ] + [
                f"{item['reference']} | {item['quantity']} | {item.get('notes') or ''}"
                for item in items
            ] + ["", "Thank you,", "Ricardo Lugo"]
        )
        return body_text, body_html

    @staticmethod
    def _attachments(rfq_id: int) -> list[dict]:
        return [{
            "path": document["stored_filename"],
            "filename": document["original_filename"],
            "mime_type": document.get("mime_type"),
        } for document in RFQRepository.list_documents(rfq_id)]

    @classmethod
    def send_test(cls, rfq_id: int) -> int:
        rfq = RFQService.require(rfq_id)
        groups = defaultdict(list)
        for item in RFQRepository.list_items(rfq_id):
            groups[str(item.get("brand") or "").strip()].append(item)
        if not groups:
            raise ValueError("La RFQ no tiene líneas para probar.")
        number = rfq["rfq_number"]
        sent = 0
        for brand, items in groups.items():
            body_text, body_html = cls._message(
                number, items, rfq.get("vendor_message")
            )
            try:
                current_app.extensions["gmail_provider"].send(
                    sender=cls.TEST_RECIPIENT,
                    recipients=[cls.TEST_RECIPIENT], cc=[],
                    subject=f"[PRUEBA] {number} - {brand}",
                    body_text=body_text, body_html=body_html,
                    attachments=cls._attachments(rfq_id),
                )
            except Exception as error:
                raise ValueError("No fue posible enviar el correo de prueba.") from error
            sent += 1
        return sent

    @staticmethod
    @transactional
    def send(rfq_id: int, actor_user_id: int) -> int:
        rfq = RFQService.require(rfq_id)
        groups = defaultdict(list)
        for item in RFQRepository.list_items(rfq_id):
            groups[str(item.get("brand") or "").strip()].append(item)
        if not groups:
            raise ValueError("La RFQ no tiene líneas para solicitar.")
        configs = {}
        with connection_scope() as connection:
            for brand in groups:
                row = connection.execute(
                    """SELECT * FROM quote_vendor_configs
                    WHERE brand=? COLLATE NOCASE AND active=1""", (brand,)
                ).fetchone()
                if row:
                    configs[brand] = dict(row)
        missing = sorted(set(groups) - set(configs))
        if missing:
            raise ValueError(
                "Falta configuración de proveedor para: " + ", ".join(missing) + "."
            )
        sent = 0
        number = rfq["rfq_number"]
        for brand, items in groups.items():
            config = configs[brand]
            existing = RFQVendorRequestRepository.latest_for_brand(rfq_id, brand)
            if existing and existing.get("status") in {"sent", "responded"}:
                raise ValueError(f"La solicitud a {brand} ya fue enviada.")
            subject = f"{number} - {brand}"
            body_text, body_html = RFQVendorRequestService._message(
                number, items, rfq.get("vendor_message")
            )
            cc = json.loads(config["default_cc_json"])
            try:
                result = current_app.extensions["gmail_provider"].send(
                    sender="ricardo.lugo@lugohermanos.com",
                    recipients=[config["vendor_email"]], cc=cc, subject=subject,
                    body_text=body_text, body_html=body_html,
                    attachments=RFQVendorRequestService._attachments(rfq_id),
                )
            except Exception as error:
                raise ValueError(
                    f"La RFQ se conservó; no se pudo enviar la solicitud a {brand}."
                ) from error
            with connection_scope() as connection:
                cursor = connection.execute(
                    """INSERT INTO rfq_vendor_requests(rfq_id,brand,vendor_config_id,
                    status,recipient_email,cc_json,subject,body_text,body_html,
                    provider_message_id,provider_thread_id,sent_by_user_id,sent_at)
                    VALUES (?,?,?,'sent',?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
                    (
                        rfq_id,brand,config["id"],config["vendor_email"],json.dumps(cc),
                        subject,body_text,body_html,result.get("message_id"),
                        result.get("thread_id"),actor_user_id,
                    ),
                )
                vendor_request_id = int(cursor.lastrowid)
            RFQVendorRequestRepository.save_message(vendor_request_id, {
                "id": result["message_id"], "direction": "outgoing",
                "sender": "ricardo.lugo@lugohermanos.com",
                "recipients": [config["vendor_email"]], "cc": cc,
                "subject": subject, "body_text": body_text,
                "body_html": body_html, "date": None,
            })
            sent += 1
        RFQRepository.update_status(rfq_id, "sent", "sent")
        RFQRepository.add_history(
            rfq_id,rfq.get("workflow_status"),"sent",actor_user_id,
            f"{sent} solicitud(es) enviadas a proveedores",
        )
        return sent

    @staticmethod
    @transactional
    def sync(rfq_id: int, actor_user_id: int) -> int:
        rfq = RFQService.require(rfq_id)
        requests = RFQVendorRequestRepository.list_for_rfq(rfq_id)
        if not requests:
            raise ValueError("La RFQ todavía no se ha enviado a un proveedor.")
        response_count = 0
        for vendor_request in requests:
            thread_id = vendor_request.get("provider_thread_id")
            if not thread_id:
                continue
            try:
                messages = current_app.extensions["gmail_provider"].thread(thread_id)
                provider = current_app.extensions["gmail_provider"]
                if hasattr(provider, "search"):
                    number = str(rfq["rfq_number"]).replace('"', "")
                    recipient = str(vendor_request["recipient_email"]).strip()
                    brand = str(vendor_request["brand"]).replace('"', "")
                    messages.extend(provider.search(f'from:{recipient} "{number}"'))
                    # Some vendor systems (including quotation portals) send the
                    # answer from an alias and start a completely new thread.
                    messages.extend(provider.search(
                        f'subject:"{number}" "{brand}"'
                    ))
                messages = list({message["id"]: message for message in messages}.values())
                has_response = False
                for message in messages:
                    message["body_html"] = RFQVendorRequestService._safe_html(
                        message.get("body_text")
                    )
                    message_id = RFQVendorRequestRepository.save_message(
                        vendor_request["id"], message
                    )
                    incoming = message.get("direction") == "incoming"
                    if incoming:
                        RFQVendorRequestService._save_attachments(
                            rfq_id, message_id, message.get("attachments") or []
                        )
                    has_response = has_response or incoming
                RFQVendorRequestRepository.mark_synced(
                    vendor_request["id"], has_response
                )
                response_count += int(has_response)
            except Exception as error:
                RFQVendorRequestRepository.mark_error(vendor_request["id"], str(error))
                raise ValueError(
                    f"No fue posible sincronizar la respuesta de {vendor_request['brand']}."
                ) from error
        refreshed = RFQVendorRequestRepository.list_for_rfq(rfq_id)
        responded = sum(bool(item["has_response"]) for item in refreshed)
        workflow = "answered" if responded == len(refreshed) else "in_progress"
        current = rfq.get("workflow_status") or "sent"
        RFQRepository.update_status(rfq_id, "analysis", workflow)
        if workflow != current:
            RFQRepository.add_history(
                rfq_id, current, workflow, actor_user_id,
                f"{responded} de {len(refreshed)} proveedor(es) respondieron",
            )
        return response_count

    @classmethod
    def sync_pending(cls, actor_user_id: int) -> dict[str, int]:
        rfq_ids = RFQVendorRequestRepository.pending_rfq_ids()
        result = {"checked": 0, "responses": 0, "errors": 0}
        for rfq_id in rfq_ids:
            before = sum(
                bool(item["has_response"])
                for item in RFQVendorRequestRepository.list_for_rfq(rfq_id)
            )
            try:
                cls.sync(rfq_id, actor_user_id)
                after = sum(
                    bool(item["has_response"])
                    for item in RFQVendorRequestRepository.list_for_rfq(rfq_id)
                )
                result["checked"] += 1
                result["responses"] += max(after - before, 0)
            except ValueError:
                current_app.logger.exception(
                    "No fue posible sincronizar la RFQ %s", rfq_id
                )
                result["errors"] += 1
        return result

    @staticmethod
    def _safe_html(value) -> str:
        return "<p>" + html.escape(str(value or "")).replace("\n", "<br>") + "</p>"

    @staticmethod
    def _save_attachments(rfq_id: int, message_id: int, attachments: list[dict]) -> None:
        folder = upload_path("rfqs", str(rfq_id), "vendor-responses")
        folder.mkdir(parents=True, exist_ok=True)
        for attachment in attachments:
            data = attachment.get("data")
            if not isinstance(data, bytes) or len(data) > 15 * 1024 * 1024:
                continue
            original = secure_filename(attachment.get("filename") or "adjunto")
            if not original:
                continue
            identity = f"{message_id}:{attachment.get('id')}:{original}".encode()
            destination = folder / f"{sha256(identity).hexdigest()[:24]}-{original}"
            if not destination.exists():
                destination.write_bytes(data)
            RFQVendorRequestRepository.save_attachment(message_id, {
                "provider_attachment_id": attachment.get("id"),
                "original_filename": original,
                "stored_filename": str(destination),
                "mime_type": attachment.get("mime_type"),
                "size_bytes": len(data),
            })
