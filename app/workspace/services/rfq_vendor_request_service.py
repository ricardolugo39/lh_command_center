import html
import json
from collections import defaultdict

from flask import current_app

from app.database.transaction import connection_scope, transactional
from app.workspace.repositories.rfq_repository import RFQRepository
from app.workspace.repositories.rfq_vendor_request_repository import (
    RFQVendorRequestRepository,
)
from app.workspace.services.rfq_service import RFQService


class RFQVendorRequestService:
    TEST_RECIPIENT = "ricardo.lugo@lugohermanos.com"

    @staticmethod
    def _message(number: str, items: list[dict]) -> tuple[str, str]:
        rows = "".join(
            "<tr>" + "".join(
                f"<td style='padding:6px;border:1px solid #ddd'>{html.escape(str(value or ''))}</td>"
                for value in (
                    item.get("reference"), item.get("quantity"),
                    item.get("notes"),
                )
            ) + "</tr>" for item in items
        )
        body_html = (
            f"<p><strong>RFQ {html.escape(number)}</strong></p>"
            "<p>Please provide price, availability, lead time and validity. "
            f"Please keep <strong>{html.escape(number)}</strong> in the subject.</p>"
            "<table style='border-collapse:collapse'><thead><tr><th>Product</th>"
            "<th>Quantity</th><th>Comments</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
        body_text = "\n".join(
            [
                f"RFQ {number}",
                "Please provide price, availability, lead time and validity. "
                f"Please keep {number} in the subject.",
            ] + [
                f"{item['reference']} | {item['quantity']} | {item.get('notes') or ''}"
                for item in items
            ]
        )
        return body_text, body_html

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
            body_text, body_html = cls._message(number, items)
            try:
                current_app.extensions["gmail_provider"].send(
                    sender=cls.TEST_RECIPIENT,
                    recipients=[cls.TEST_RECIPIENT], cc=[],
                    subject=f"[PRUEBA] RFQ {number} - {brand}",
                    body_text=body_text, body_html=body_html,
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
            subject = f"RFQ {number} - {brand}"
            body_text, body_html = RFQVendorRequestService._message(number, items)
            cc = json.loads(config["default_cc_json"])
            try:
                result = current_app.extensions["gmail_provider"].send(
                    sender="ricardo.lugo@lugohermanos.com",
                    recipients=[config["vendor_email"]], cc=cc, subject=subject,
                    body_text=body_text, body_html=body_html,
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
                has_response = False
                for message in messages:
                    message["body_html"] = RFQVendorRequestService._safe_html(
                        message.get("body_text")
                    )
                    RFQVendorRequestRepository.save_message(
                        vendor_request["id"], message
                    )
                    has_response = has_response or message.get("direction") == "incoming"
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

    @staticmethod
    def _safe_html(value) -> str:
        return "<p>" + html.escape(str(value or "")).replace("\n", "<br>") + "</p>"
