from datetime import date, timedelta
from html import escape
from pathlib import Path
from typing import Any

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.database.transaction import connection_scope, transactional
from app.workspace.repositories.quote_management_repository import (
    QuoteManagementRepository,
)
from app.workspace.repositories.rfq_repository import RFQRepository
from app.workspace.services.quote_calculation_service import QuoteCalculationService
from app.workspace.services.rfq_service import RFQService
from app.workspace.repositories.customer_repository import CustomerRepository
from app.workspace.repositories.contact_repository import ActivityFormRepository


PDF_ROOT = Path("output/pdf")
QUOTE_STATUSES = {
    "draft": "Borrador", "waiting_vendor": "Esperando proveedor",
    "partial_vendor_response": "Respuesta parcial", "ready_pricing": "Lista para costear",
    "ready_review": "Lista para revisión", "ready_issue": "Lista para emitir",
    "sent_sales_rep": "Enviada al asesor", "sent_customer": "Enviada al cliente",
    "followup_due": "Seguimiento vencido", "won": "Ganada", "lost": "Perdida",
    "cancelled": "Cancelada", "expired": "Vencida",
}


class QuoteManagementService:
    @staticmethod
    @transactional
    def create_direct(values: dict[str, Any], actor_user_id: int) -> int:
        customer_id = RFQService._integer(values.get("customer_id"))
        new_name = str(values.get("new_customer_name") or "").strip()
        if not customer_id and new_name:
            existing = CustomerRepository.find_by_name(new_name)
            customer_id = (
                existing["id"] if existing
                else CustomerRepository.create_customer(new_name)
            )
        if not customer_id or not ActivityFormRepository.get_customer(customer_id):
            raise ValueError("Seleccione o registre un cliente válido.")
        sales_rep_name = str(values.get("sales_rep_name") or "").strip()
        sales_rep_email = str(values.get("sales_rep_email") or "").strip().casefold()
        if not sales_rep_name:
            raise ValueError("Indique el asesor comercial.")
        if "@" not in sales_rep_email:
            raise ValueError("Indique un correo válido para el asesor.")
        items = values.get("items") or []
        if not items:
            raise ValueError("Agregue al menos un producto.")
        clean_items = []
        for index, item in enumerate(items, 1):
            reference = str(item.get("reference") or "").strip()
            brand = str(item.get("brand") or "").strip()
            lead_time = str(item.get("lead_time") or "").strip()
            quantity = RFQService._number(item.get("quantity"))
            fob = RFQService._number(item.get("fob_unit_usd"))
            weight = RFQService._number(item.get("unit_weight_kg"))
            if not reference or not brand:
                raise ValueError(f"Complete referencia y marca en la fila {index}.")
            if not quantity or quantity <= 0 or not fob or fob <= 0 or not weight or weight <= 0:
                raise ValueError(f"Cantidad, precio USD y peso deben ser positivos en la fila {index}.")
            if not lead_time:
                raise ValueError(f"Indique el tiempo de entrega en la fila {index}.")
            clean_items.append({
                **item, "reference": reference, "brand": brand,
                "lead_time": lead_time, "quantity": quantity,
                "fob_unit_usd": fob, "unit_weight_kg": weight,
                "display_order": index - 1,
                "source_note": str(item.get("source_note") or "").strip() or None,
                "notes": str(item.get("notes") or "").strip() or None,
            })
        quote_id = QuoteManagementRepository.create_direct({
            "customer_id": customer_id, "sales_rep_name": sales_rep_name,
            "sales_rep_email": sales_rep_email,
            "comments": str(values.get("comments") or "").strip() or None,
        }, actor_user_id)
        for item in clean_items:
            QuoteManagementRepository.add_direct_line(quote_id, item)
        return quote_id

    @staticmethod
    @transactional
    def delete_draft(quote_id: int) -> int | None:
        quote = QuoteManagementRepository.get(quote_id)
        if not quote:
            raise ValueError("La cotización no existe.")
        if quote.get("issued_at") or quote.get("sent_at") or quote.get("quote_status") != "draft":
            raise ValueError("Solo se puede eliminar una versión en borrador no emitida.")
        with connection_scope() as connection:
            child = connection.execute(
                "SELECT 1 FROM ws_project_quotes WHERE revised_from_quote_id=? LIMIT 1",
                (quote_id,),
            ).fetchone()
        if child:
            raise ValueError("Elimine primero la revisión posterior de esta cotización.")
        project_id = quote.get("project_id")
        QuoteManagementRepository.delete_draft(quote_id)
        return int(project_id) if project_id else None

    @staticmethod
    @transactional
    def create_from_rfq(rfq_id: int, actor_user_id: int) -> int:
        rfq = RFQService.require(rfq_id)
        if (rfq.get("workflow_status") or "draft") == "cancelled":
            raise ValueError("Una RFQ cancelada no puede convertirse.")
        items = RFQRepository.list_items(rfq_id)
        if not items:
            raise ValueError("La RFQ no tiene líneas para cotizar.")
        quote_id = QuoteManagementRepository.create_from_rfq(rfq, actor_user_id)
        QuoteManagementRepository.copy_rfq_lines(quote_id, rfq_id)
        QuoteManagementRepository.copy_rfq_attachments(quote_id, rfq_id)
        RFQRepository.update_status(rfq_id, "preparing", "closed", rfq.get("opportunity_id"))
        RFQRepository.add_history(
            rfq_id, rfq.get("workflow_status"), "converted_to_quote",
            actor_user_id, f"Convertida a cotización RL-{QuoteManagementRepository.get(quote_id)['quote_number']}",
        )
        return quote_id

    @staticmethod
    def workspace(quote_id: int) -> dict[str, Any]:
        quote = QuoteManagementRepository.get(quote_id)
        if not quote:
            raise ValueError("La cotización no existe.")
        profile = QuoteManagementRepository.active_profile()
        return {
            "quote": quote,
            "lines": QuoteManagementRepository.lines(quote_id),
            "origins": QuoteManagementRepository.origin_options(profile["id"]) if profile else [],
            "pricing_rules": QuoteManagementRepository.pricing_rules(),
            "attachments": QuoteManagementRepository.attachments(quote_id),
            "pdf": QuoteManagementRepository.latest_pdf(quote_id),
            "statuses": QUOTE_STATUSES,
        }

    @staticmethod
    @transactional
    def save_workspace(
        quote_id: int, header: dict[str, Any], line_values: list[dict[str, Any]],
        actor_user_id: int,
    ) -> None:
        quote = QuoteManagementRepository.get(quote_id)
        if not quote or quote.get("issued_at"):
            raise ValueError("La revisión emitida es inmutable.")
        origin = str(header.get("origin_option") or "").split("|", 1)
        if len(origin) == 2:
            header["origin_country_code"] = origin[0]
            header["origin_service_area_code"] = origin[1]
        manual_shipping = str(header.get("manual_shipping_usd") or "").strip()
        if manual_shipping and (self_value := RFQService._number(manual_shipping)) is not None and self_value < 0:
            raise ValueError("El costo de envío manual no puede ser negativo.")
        QuoteManagementRepository.update_header(quote_id, header, actor_user_id)
        existing = {line["id"] for line in QuoteManagementRepository.lines(quote_id)}
        for values in line_values:
            if values["id"] not in existing:
                raise ValueError("Una línea no pertenece a esta cotización.")
            QuoteManagementRepository.update_line(values["id"], values, actor_user_id)

    @staticmethod
    @transactional
    def calculate(quote_id: int) -> dict[str, Any]:
        quote = QuoteManagementRepository.get(quote_id)
        if not quote:
            raise ValueError("La cotización no existe.")
        result = QuoteCalculationService.calculate(
            quote, QuoteManagementRepository.lines(quote_id)
        )
        QuoteManagementRepository.save_calculation(
            quote_id, result["quote"], result["lines"]
        )
        return result

    @staticmethod
    @transactional
    def new_revision(quote_id: int, actor_user_id: int) -> int:
        source = QuoteManagementRepository.get(quote_id)
        if not source:
            raise ValueError("La cotización no existe.")
        with connection_scope() as connection:
            next_revision = connection.execute(
                "SELECT COALESCE(MAX(revision),0)+1 FROM ws_project_quotes WHERE quote_series_key=?",
                (source["quote_series_key"],),
            ).fetchone()[0]
            columns = [
                row["name"] for row in connection.execute("PRAGMA table_info(ws_project_quotes)")
                if row["name"] not in {"id", "created_at", "revision", "revised_from_quote_id", "ready_at", "issued_at", "sent_at"}
            ]
            cursor = connection.execute(
                f"INSERT INTO ws_project_quotes({','.join(columns)},revision,revised_from_quote_id) "
                f"SELECT {','.join(columns)},?,? FROM ws_project_quotes WHERE id=?",
                (next_revision, quote_id, quote_id),
            )
            new_id = int(cursor.lastrowid)
            line_columns = [
                row["name"] for row in connection.execute("PRAGMA table_info(ws_quote_lines)")
                if row["name"] not in {"id", "quote_id", "created_at", "updated_at"}
            ]
            connection.execute(
                f"INSERT INTO ws_quote_lines(quote_id,{','.join(line_columns)}) "
                f"SELECT ?,{','.join(line_columns)} FROM ws_quote_lines WHERE quote_id=?",
                (new_id, quote_id),
            )
            connection.execute(
                """INSERT INTO quote_attachment_links(quote_id,rfq_document_id,
                original_filename,stored_filename,mime_type,size_bytes,category,
                uploaded_by_user_id,included_in_delivery,vendor_confidential)
                SELECT ?,rfq_document_id,original_filename,stored_filename,mime_type,
                size_bytes,category,uploaded_by_user_id,included_in_delivery,vendor_confidential
                FROM quote_attachment_links WHERE quote_id=?""", (new_id,quote_id)
            )
        return new_id

    @staticmethod
    def validate_for_issue(quote: dict[str, Any], lines: list[dict[str, Any]]) -> None:
        missing = []
        for field, label in (
            ("customer_id", "cliente"), ("sales_rep_name", "asesor"),
            ("sales_rep_email", "correo del asesor"), ("origin_country_code", "país de origen"),
            ("final_dhl_zone", "zona DHL"), ("amount", "total"),
        ):
            if not quote.get(field):
                missing.append(label)
        if not lines:
            missing.append("líneas")
        if missing:
            raise ValueError("Faltan datos para emitir: " + ", ".join(missing) + ".")

    @staticmethod
    @transactional
    def generate_pdf(quote_id: int, actor_user_id: int) -> Path:
        page = QuoteManagementService.workspace(quote_id)
        if not page["quote"].get("amount") or not page["quote"].get("final_dhl_zone"):
            QuoteManagementService.calculate(quote_id)
            page = QuoteManagementService.workspace(quote_id)
        quote, lines = page["quote"], page["lines"]
        QuoteManagementService.validate_for_issue(quote, lines)
        PDF_ROOT.mkdir(parents=True, exist_ok=True)
        filename = f"{quote['prefix']}-{quote['quote_number']}-R{quote['revision']}.pdf"
        path = PDF_ROOT / filename
        styles = getSampleStyleSheet()
        title = ParagraphStyle("title", parent=styles["Title"], textColor=colors.HexColor("#17365D"), alignment=TA_CENTER)
        doc = SimpleDocTemplate(str(path), pagesize=letter, rightMargin=15*mm, leftMargin=15*mm, topMargin=14*mm, bottomMargin=14*mm)
        story = [
            Paragraph("LUGO HERMANOS S.A.", title),
            Paragraph("COTIZACIÓN COMERCIAL", ParagraphStyle("sub", parent=styles["Heading2"], alignment=TA_CENTER)),
            Spacer(1, 5*mm),
            Table([
                ["Cotización", f"{quote['prefix']}-{quote['quote_number']} · Revisión {quote['revision']}", "Fecha", quote.get("quote_date") or date.today().isoformat()],
                ["Cliente", quote.get("customer_name") or "", "Asesor", quote.get("sales_rep_name") or ""],
                ["Correo", quote.get("sales_rep_email") or "", "Moneda", "USD"],
            ], colWidths=[24*mm,65*mm,20*mm,70*mm], style=TableStyle([
                ("BACKGROUND",(0,0),(0,-1),colors.HexColor("#E8EEF6")),
                ("BACKGROUND",(2,0),(2,-1),colors.HexColor("#E8EEF6")),
                ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#B7C3D0")),
                ("FONTNAME",(0,0),(-1,-1),"Helvetica"), ("FONTSIZE",(0,0),(-1,-1),8),
                ("VALIGN",(0,0),(-1,-1),"MIDDLE"), ("PADDING",(0,0),(-1,-1),5),
            ])), Spacer(1,5*mm)
        ]
        data = [["Item", "Cantidad", "Referencia", "Marca", "Precio unitario USD", "Entrega"]]
        for index, line in enumerate(lines, 1):
            data.append([
                index, f"{line['quantity']:g}", line.get("part_number") or "",
                line.get("brand") or "", f"USD {float(line.get('selling_unit_usd') or 0):,.2f}",
                line.get("lead_time") or "",
            ])
        data.append(["", "", "", "TOTAL", f"USD {float(quote.get('amount') or 0):,.2f}", ""])
        story.extend([Table(data, colWidths=[12*mm,20*mm,42*mm,27*mm,43*mm,35*mm], repeatRows=1, style=TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("GRID",(0,0),(-1,-2),0.4,colors.HexColor("#B7C3D0")), ("FONTSIZE",(0,0),(-1,-1),8),
            ("ALIGN",(1,1),(1,-1),"CENTER"), ("ALIGN",(4,1),(4,-1),"RIGHT"),
            ("BACKGROUND",(3,-1),(4,-1),colors.HexColor("#E8EEF6")), ("FONTNAME",(3,-1),(4,-1),"Helvetica-Bold"),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"), ("PADDING",(0,0),(-1,-1),5),
        ])), Spacer(1,5*mm)])
        if quote.get("commercial_comments"):
            story.extend([Paragraph("Comentarios comerciales", styles["Heading3"]), Paragraph(escape(quote["commercial_comments"]), styles["BodyText"]), Spacer(1,3*mm)])
        story.extend([
            Paragraph("Condiciones comerciales", styles["Heading3"]),
            Paragraph("• Valores expresados en dólares estadounidenses (USD).<br/>• Los precios aplican únicamente para la cantidad completa indicada.<br/>• Disponibilidad sujeta a confirmación de fábrica.<br/>• Vigencia de la oferta: 10 días.", styles["BodyText"]),
        ])
        doc.build(story)
        QuoteManagementRepository.save_pdf(quote_id, str(path), actor_user_id)
        with connection_scope() as connection:
            connection.execute(
                "UPDATE ws_project_quotes SET quote_status='ready_issue',ready_at=CURRENT_TIMESTAMP WHERE id=?",
                (quote_id,),
            )
        return path

    @staticmethod
    @transactional
    def prepare_delivery(
        quote_id: int, actor: int, review: dict[str, Any] | None = None
    ) -> int:
        page = QuoteManagementService.workspace(quote_id)
        quote, lines = page["quote"], page["lines"]
        if not page["pdf"]:
            QuoteManagementService.generate_pdf(quote_id, actor)
        products = ", ".join(dict.fromkeys(line.get("part_number") or line["description"] for line in lines))[:80]
        brands = ", ".join(dict.fromkeys(line.get("brand") or "" for line in lines if line.get("brand")))
        subject = f"Cotización: {quote['customer_name']} - {quote['prefix']}-{quote['quote_number']} - {products} ({brands})"[:180]
        text = f"Hola {quote.get('sales_rep_name') or ''},\n\nAdjunto cotización.\n\nQuedo atento.\nRicardo Lugo"
        review = review or {}
        recipient = str(review.get("recipient_email") or quote["sales_rep_email"]).strip()
        if not recipient:
            raise ValueError("La entrega requiere destinatario.")
        cc = [item.strip() for item in str(review.get("cc") or "").split(",") if item.strip()]
        advisor_note = str(review.get("advisor_note") or "").strip()
        body_text = str(review.get("body_text") or text)
        if advisor_note:
            body_text += f"\n\nNota para el asesor:\n{advisor_note}"
        body_html = "<p>" + escape(body_text).replace("\n", "<br>") + "</p>"
        return QuoteManagementRepository.save_delivery(quote_id, {
            "recipient_email": recipient, "cc": cc,
            "subject": str(review.get("subject") or subject).strip(),
            "body_text": body_text, "body_html": body_html,
            "advisor_note": advisor_note, "note_internal_only": bool(review.get("note_internal_only")),
            "note_included": bool(advisor_note),
            "attachment_ids": review.get("attachment_ids", []),
        }, actor)

    @staticmethod
    @transactional
    def send_delivery(delivery_id: int, actor: int) -> None:
        delivery = QuoteManagementRepository.get_delivery(delivery_id)
        if not delivery:
            raise ValueError("El borrador de entrega no existe.")
        quote = QuoteManagementRepository.get(delivery["quote_id"])
        pdf = QuoteManagementRepository.latest_pdf(delivery["quote_id"])
        if not quote or not pdf:
            raise ValueError("La entrega no tiene una cotización PDF.")
        import json
        requested_ids = {str(value) for value in json.loads(delivery["attachment_ids_json"])}
        attachments = [{
            "path": pdf["stored_filename"],
            "filename": Path(pdf["stored_filename"]).name,
            "mime_type": "application/pdf",
        }]
        for item in QuoteManagementRepository.attachments(quote["id"]):
            if (
                str(item["id"]) in requested_ids
                and not item.get("vendor_confidential")
                and item.get("stored_filename")
                and Path(item["stored_filename"]).is_file()
            ):
                attachments.append({
                    "path": item["stored_filename"],
                    "filename": item["original_filename"],
                    "mime_type": item.get("mime_type"),
                })
        try:
            result = current_app.extensions["gmail_provider"].send(
                sender="ricardo.lugo@lugohermanos.com",
                recipients=[delivery["recipient_email"]],
                cc=json.loads(delivery["cc_json"]), subject=delivery["subject"],
                body_text=delivery["body_text"], body_html=delivery["body_html"],
                attachments=attachments,
            )
        except Exception as error:
            QuoteManagementRepository.mark_delivery_error(delivery_id, str(error))
            raise ValueError("La cotización se conservó, pero Gmail no pudo enviarla.") from error
        QuoteManagementRepository.mark_delivery_sent(delivery_id, result, actor)
        settings = QuoteManagementRepository.settings()
        due = date.today()
        remaining = int(settings.get("followup_business_days", "3"))
        while remaining:
            due += timedelta(days=1)
            if due.weekday() < 5:
                remaining -= 1
        with connection_scope() as connection:
            connection.execute(
                """UPDATE ws_project_quotes SET quote_status='sent_sales_rep',
                issued_at=COALESCE(issued_at,CURRENT_TIMESTAMP),sent_at=CURRENT_TIMESTAMP
                WHERE id=?""", (quote["id"],)
            )
            connection.execute(
                """INSERT INTO quote_followups(quote_id,assigned_user_id,due_date,description)
                VALUES (?,?,?,?)""", (
                    quote["id"], quote.get("sales_rep_user_id"), due.isoformat(),
                    f"Seguimiento cotización {quote['prefix']}-{quote['quote_number']}",
                )
            )

    @staticmethod
    @transactional
    def record_outcome(quote_id: int, values: dict[str, Any], actor: int) -> None:
        outcome = str(values.get("outcome") or "")
        if outcome not in {"won", "lost", "cancelled"}:
            raise ValueError("Resultado no válido.")
        if outcome == "lost" and not str(values.get("loss_reason") or "").strip():
            raise ValueError("Una cotización perdida requiere motivo.")
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO quote_outcomes(quote_id,outcome,final_order_amount_usd,
                customer_po,order_number,loss_reason,competitor,comments,outcome_date,
                recorded_by_user_id) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(quote_id) DO UPDATE SET outcome=excluded.outcome,
                final_order_amount_usd=excluded.final_order_amount_usd,
                customer_po=excluded.customer_po,order_number=excluded.order_number,
                loss_reason=excluded.loss_reason,competitor=excluded.competitor,
                comments=excluded.comments,outcome_date=excluded.outcome_date,
                recorded_by_user_id=excluded.recorded_by_user_id""", (
                    quote_id,outcome,values.get("final_order_amount_usd"),values.get("customer_po"),
                    values.get("order_number"),values.get("loss_reason"),values.get("competitor"),
                    values.get("comments"),values.get("outcome_date") or date.today().isoformat(),actor,
                )
            )
            connection.execute(
                "UPDATE ws_project_quotes SET quote_status=? WHERE id=?", (outcome,quote_id)
            )
