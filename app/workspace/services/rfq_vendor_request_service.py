import html
import json
from collections import defaultdict

from flask import current_app

from app.database.transaction import connection_scope, transactional
from app.workspace.repositories.rfq_repository import RFQRepository
from app.workspace.services.rfq_service import RFQService


class RFQVendorRequestService:
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
        number = rfq.get("prequotation_number") or rfq["rfq_number"]
        for brand, items in groups.items():
            config = configs[brand]
            subject = f"RFQ for {brand} - Precotización #{number}"
            rows = "".join(
                "<tr>" + "".join(
                    f"<td style='padding:6px;border:1px solid #ddd'>{html.escape(str(value or ''))}</td>"
                    for value in (item.get("reference"), item.get("quantity"), item.get("notes"))
                ) + "</tr>" for item in items
            )
            body_html = (
                "<p>Please provide price, availability, lead time and validity.</p>"
                "<table style='border-collapse:collapse'><thead><tr><th>Product</th><th>Quantity</th><th>Comments</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>"
            )
            body_text = "\n".join(
                ["Please provide price, availability, lead time and validity."]
                + [f"{item['reference']} | {item['quantity']} | {item.get('notes') or ''}" for item in items]
            )
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
                connection.execute(
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
            sent += 1
        RFQRepository.update_status(rfq_id, "sent", "sent")
        RFQRepository.add_history(
            rfq_id,rfq.get("workflow_status"),"sent",actor_user_id,
            f"{sent} solicitud(es) enviadas a proveedores",
        )
        return sent
