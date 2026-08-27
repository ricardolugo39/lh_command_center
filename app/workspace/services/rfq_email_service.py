import html
from typing import Any

from flask import current_app

from app.configuration import resolve_settings
from app.database.transaction import transactional
from app.workspace.repositories.rfq_email_repository import RFQEmailRepository
from app.workspace.repositories.rfq_repository import RFQRepository
from app.workspace.services.rfq_service import RFQService


class RFQEmailService:
    @classmethod
    def send(cls, rfq_id: int) -> None:
        rfq = RFQService.require(rfq_id)
        if RFQEmailRepository.get_thread(rfq_id):
            raise ValueError("La solicitud ya fue enviada por correo.")
        items = RFQRepository.list_items(rfq_id)
        sender, recipient, cc = cls._addresses(rfq)
        brands = {item.get("brand") for item in items if item.get("brand")}
        brand_summary = next(iter(brands)) if len(brands) == 1 else "Varias marcas"
        number = rfq.get("prequotation_number") or rfq["rfq_number"]
        subject = f"Precotización {number} | {rfq['customer_name']} | {brand_summary}"
        body_text, body_html = cls._body(rfq, items, number, sender)
        try:
            result = current_app.extensions["gmail_provider"].send(
                sender=sender, recipients=[recipient], cc=cc, subject=subject,
                body_text=body_text, body_html=body_html,
            )
        except Exception as error:
            current_app.logger.exception("No se pudo enviar la RFQ por Gmail")
            raise ValueError(
                "La RFQ se conservó, pero no fue posible enviarla por Gmail."
            ) from error
        cls._complete_send(
            rfq_id, subject, sender, recipient, cc, result, body_text, body_html
        )

    @classmethod
    @transactional
    def _complete_send(
        cls, rfq_id, subject, sender, recipient, cc, result, body_text, body_html
    ):
        RFQEmailRepository.save_sent(
            rfq_id, subject=subject, sender=sender, recipients=[recipient],
            cc=cc, provider_thread_id=result["thread_id"],
            provider_message_id=result["message_id"], body_text=body_text,
            body_html=body_html,
        )
        RFQService.advance(rfq_id, status="sent", comment="Enviada por Gmail")

    @classmethod
    @transactional
    def sync(cls, rfq_id: int) -> None:
        thread = RFQEmailRepository.get_thread(rfq_id)
        if not thread or not thread.get("provider_thread_id"):
            raise ValueError("La RFQ todavía no tiene una conversación de Gmail.")
        try:
            messages = current_app.extensions["gmail_provider"].thread(
                thread["provider_thread_id"]
            )
            for message in messages:
                message["body_html"] = cls._safe_html(message.get("body_text"))
            RFQEmailRepository.save_messages(rfq_id, messages)
        except Exception as error:
            RFQEmailRepository.mark_error(rfq_id, str(error))
            raise ValueError("No fue posible sincronizar los correos.") from error

    @staticmethod
    def _addresses(rfq):
        values, _ = resolve_settings((
            "RFQ_DEFAULT_SENDER_EMAIL", "RFQ_ALWAYS_CC_EMAIL",
        ))
        sender = values.get(
            "RFQ_DEFAULT_SENDER_EMAIL", "ricardo.lugo@lugohermanos.com"
        ).strip().casefold()
        recipient = str(rfq.get("owner_email") or "").strip().casefold()
        if not recipient:
            raise ValueError("El responsable no tiene un correo configurado.")
        cc_value = values.get(
            "RFQ_ALWAYS_CC_EMAIL", "ricardo.lugo@lugohermanos.com"
        ).strip().casefold()
        cc = [cc_value] if cc_value and cc_value not in {sender, recipient} else []
        return sender, recipient, cc

    @staticmethod
    def _body(rfq, items, number, sender):
        esc = html.escape
        rows = "".join(
            "<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #ddd'>{esc(str(item['reference']))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #ddd'>{esc(str(item['brand']))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #ddd'>{esc(str(item['quantity']))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #ddd'>{esc(str(item.get('notes') or ''))}</td>"
            "</tr>" for item in items
        )
        text = (
            f"Solicitud de precotización {number}\nCliente: {rfq['customer_name']}\n"
            "Por favor responder con precio, disponibilidad, tiempo de entrega, "
            "condiciones comerciales y vigencia. Conserve el número de "
            "precotización en el asunto."
        )
        markup = (
            "<div style='font-family:Arial,sans-serif;color:#24324a'>"
            "<h2>Solicitud de precotización</h2>"
            f"<p><strong>Número:</strong> {esc(number)}<br>"
            f"<strong>Cliente:</strong> {esc(rfq['customer_name'])}<br>"
            f"<strong>Solicitado por:</strong> {esc(sender)}<br>"
            f"<strong>Responsable:</strong> {esc(rfq['owner_name'])}<br>"
            f"<strong>Fecha:</strong> {esc(str(rfq['received_at']))}</p>"
            "<table style='border-collapse:collapse;width:100%'><thead><tr>"
            "<th style='text-align:left;padding:8px'>Referencia</th>"
            "<th style='text-align:left;padding:8px'>Marca</th>"
            "<th style='text-align:left;padding:8px'>Cantidad</th>"
            "<th style='text-align:left;padding:8px'>Notas</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            "<p>Por favor responder con precio, disponibilidad, tiempo de entrega, "
            "condiciones comerciales y vigencia. Conserve el número de "
            "precotización en el asunto.</p></div>"
        )
        return text, markup

    @staticmethod
    def _safe_html(value: Any) -> str:
        return "<p>" + html.escape(str(value or "")).replace("\n", "<br>") + "</p>"
