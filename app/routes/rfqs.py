from datetime import date
from pathlib import Path

from flask import Blueprint, abort, g, redirect, render_template, request, send_file, url_for
from app.auth import roles_required

from app.workspace.repositories.contact_repository import (
    ActivityFormRepository,
    ContactRepository,
)
from app.workspace.repositories.rfq_repository import RFQRepository
from app.workspace.services.rfq_service import RFQService
from app.workspace.services.rfq_email_service import RFQEmailService
from app.workspace.services.quote_management_service import QuoteManagementService
from app.workspace.services.rfq_vendor_request_service import RFQVendorRequestService
from app.workspace.services.rfq_document_service import RFQDocumentService
from app.workspace.repositories.rfq_vendor_request_repository import RFQVendorRequestRepository
from app.workspace.constants.commercial_office import OFFICES


rfqs_bp = Blueprint("rfqs", __name__, url_prefix="/rfqs")


@rfqs_bp.get("/")
def index():
    status = request.args.get("status", "").strip() or None
    if status and status not in RFQService.STATUS_LABELS:
        status = None
    search = request.args.get("q", "").strip()
    office = request.args.get("office", "").strip()
    if office not in OFFICES:
        office = ""
    return render_template(
        "rfqs/index.html", rfqs=RFQRepository.list_all(status, search, office),
        status=status, labels=RFQService.STATUS_LABELS,
        search=search, office=office, offices=OFFICES,
    )


@rfqs_bp.post("/sync-pending")
@roles_required("administrator", "commercial_management")
def sync_pending_responses():
    result = RFQVendorRequestService.sync_pending(g.current_user["id"])
    return redirect(url_for("rfqs.index", sync=1, **result))


@rfqs_bp.route("/new", methods=["GET", "POST"])
@roles_required("administrator", "commercial_management", "advisor")
def new():
    error = None
    customer_id = request.form.get("customer_id", type=int) or request.args.get(
        "customer_id", type=int
    )
    if request.method == "POST":
        try:
            uploads = RFQDocumentService.validate(request.files.getlist("attachments"))
            values = request.form.to_dict()
            references = request.form.getlist("item_reference")
            vendor = request.form.get("vendor", "").strip()
            quantities = request.form.getlist("item_quantity")
            notes = request.form.getlist("item_notes")
            values["items"] = [
                {
                    "reference": reference,
                    "brand": vendor,
                    "quantity": (
                        quantities[index] if index < len(quantities) else ""
                    ),
                    "notes": notes[index] if index < len(notes) else "",
                }
                for index, reference in enumerate(references)
            ]
            rfq_id = RFQService.create(values)
            RFQDocumentService.save_many(rfq_id, uploads, g.current_user["id"])
            return redirect(url_for("rfqs.detail", rfq_id=rfq_id))
        except ValueError as exception:
            error = str(exception)
    customer = (
        ActivityFormRepository.get_customer(customer_id) if customer_id else None
    )
    contacts = (
        ContactRepository.list_for_customer(customer_id) if customer_id else []
    )
    return render_template(
        "rfqs/form.html", error=error, customer=customer,
        contacts=contacts, users=ActivityFormRepository.list_sales_users(),
        sales_representatives=ActivityFormRepository.list_sales_representatives(),
        brand_options=ActivityFormRepository.list_brand_options(),
        default_responsible_email=RFQService.default_responsible_email(),
        default_received_at=date.today().isoformat(),
        form=request.form,
    )


@rfqs_bp.get("/<int:rfq_id>")
def detail(rfq_id: int):
    try:
        page = RFQService.detail(rfq_id)
    except ValueError:
        abort(404)
    return render_template("rfqs/detail.html", page=page, error=None)


@rfqs_bp.get("/<int:rfq_id>/vendor-attachments/<int:attachment_id>")
def vendor_attachment(rfq_id: int, attachment_id: int):
    attachment = RFQVendorRequestRepository.get_attachment(rfq_id, attachment_id)
    if not attachment or not Path(attachment["stored_filename"]).is_file():
        abort(404)
    return send_file(
        Path(attachment["stored_filename"]).resolve(),
        mimetype=attachment.get("mime_type") or "application/octet-stream",
        download_name=attachment["original_filename"],
        as_attachment=False,
    )


@rfqs_bp.post("/<int:rfq_id>/delete")
@roles_required("administrator")
def delete(rfq_id: int):
    try:
        paths = RFQService.delete_draft(rfq_id)
        RFQService.remove_document_files(paths)
    except ValueError as exception:
        return render_template(
            "rfqs/detail.html", page=RFQService.detail(rfq_id),
            error=str(exception),
        ), 400
    return redirect(url_for("rfqs.index", deleted=1))


@rfqs_bp.post("/<int:rfq_id>/advance")
@roles_required("administrator", "commercial_management", "advisor")
def advance(rfq_id: int):
    try:
        RFQService.advance(
            rfq_id, status=request.form.get("status", ""),
            comment=request.form.get("comment"),
            changed_by_user_id=(
                g.current_user["id"] if getattr(g, "current_user", None) else 1
            ),
        )
    except ValueError as exception:
        return render_template(
            "rfqs/detail.html", page=RFQService.detail(rfq_id),
            error=str(exception),
        ), 400
    return redirect(url_for("rfqs.detail", rfq_id=rfq_id))


@rfqs_bp.post("/<int:rfq_id>/conclude")
@roles_required("administrator", "commercial_management", "advisor")
def conclude(rfq_id: int):
    try:
        RFQService.conclude(
            rfq_id, outcome=request.form.get("outcome", ""),
            reason=request.form.get("reason"),
            final_value=request.form.get("final_value"),
            currency_code=request.form.get("currency_code"),
            erp_sale_reference=request.form.get("erp_sale_reference"),
            concluded_by_user_id=(
                g.current_user["id"] if getattr(g, "current_user", None) else 1
            ),
        )
    except ValueError as exception:
        return render_template(
            "rfqs/detail.html", page=RFQService.detail(rfq_id),
            error=str(exception),
        ), 400
    return redirect(url_for("rfqs.detail", rfq_id=rfq_id))


@rfqs_bp.post("/<int:rfq_id>/send")
@roles_required("administrator", "commercial_management", "advisor")
def send_email(rfq_id: int):
    try:
        RFQEmailService.send(rfq_id)
    except ValueError as exception:
        return render_template(
            "rfqs/detail.html", page=RFQService.detail(rfq_id),
            error=str(exception),
        ), 400
    return redirect(url_for("rfqs.detail", rfq_id=rfq_id))


@rfqs_bp.post("/<int:rfq_id>/sync-email")
@roles_required("administrator", "commercial_management", "advisor")
def sync_email(rfq_id: int):
    try:
        RFQEmailService.sync(rfq_id)
    except ValueError as exception:
        return render_template(
            "rfqs/detail.html", page=RFQService.detail(rfq_id),
            error=str(exception),
        ), 400
    return redirect(url_for("rfqs.detail", rfq_id=rfq_id))


@rfqs_bp.post("/<int:rfq_id>/items/<int:item_id>/vendor-response")
@roles_required("administrator")
def vendor_response(rfq_id: int, item_id: int):
    try:
        RFQService.record_vendor_response(
            rfq_id, item_id, request.form.to_dict(), g.current_user["id"]
        )
    except ValueError as exception:
        return render_template(
            "rfqs/detail.html", page=RFQService.detail(rfq_id), error=str(exception)
        ), 400
    return redirect(url_for("rfqs.detail", rfq_id=rfq_id))


@rfqs_bp.post("/<int:rfq_id>/convert-to-quote")
@roles_required("administrator")
def convert_to_quote(rfq_id: int):
    try:
        quote_id = QuoteManagementService.create_from_rfq(
            rfq_id, g.current_user["id"]
        )
    except ValueError as exception:
        return render_template(
            "rfqs/detail.html", page=RFQService.detail(rfq_id), error=str(exception)
        ), 400
    return redirect(url_for("quotes.workspace", quote_id=quote_id))


@rfqs_bp.post("/<int:rfq_id>/request-vendor-prices")
@roles_required("administrator", "commercial_management")
def request_vendor_prices(rfq_id: int):
    try:
        RFQVendorRequestService.send(rfq_id, g.current_user["id"])
    except ValueError as exception:
        return render_template(
            "rfqs/detail.html", page=RFQService.detail(rfq_id), error=str(exception)
        ), 400
    return redirect(url_for("rfqs.detail", rfq_id=rfq_id))


@rfqs_bp.post("/<int:rfq_id>/test-vendor-email")
@roles_required("administrator", "commercial_management")
def test_vendor_email(rfq_id: int):
    try:
        RFQVendorRequestService.send_test(rfq_id)
    except ValueError as exception:
        return render_template(
            "rfqs/detail.html", page=RFQService.detail(rfq_id),
            error=str(exception),
        ), 400
    return redirect(url_for("rfqs.detail", rfq_id=rfq_id, test_sent=1))


@rfqs_bp.post("/<int:rfq_id>/vendor-content")
@roles_required("administrator", "commercial_management")
def vendor_content(rfq_id: int):
    try:
        page = RFQService.detail(rfq_id)
        if page["vendor_requests"]:
            raise ValueError("El contenido no se puede cambiar después del envío.")
        uploads = RFQDocumentService.validate(
            request.files.getlist("attachments")
        )
        message = request.form.get("vendor_message", "").strip() or None
        RFQRepository.update_vendor_message(rfq_id, message)
        RFQDocumentService.save_many(rfq_id, uploads, g.current_user["id"])
    except ValueError as exception:
        return render_template(
            "rfqs/detail.html", page=RFQService.detail(rfq_id),
            error=str(exception),
        ), 400
    return redirect(url_for("rfqs.detail", rfq_id=rfq_id, content_saved=1))


@rfqs_bp.post("/<int:rfq_id>/sync-vendor-responses")
@roles_required("administrator", "commercial_management")
def sync_vendor_responses(rfq_id: int):
    try:
        RFQVendorRequestService.sync(rfq_id, g.current_user["id"])
    except ValueError as exception:
        return render_template(
            "rfqs/detail.html", page=RFQService.detail(rfq_id),
            error=str(exception),
        ), 400
    return redirect(url_for("rfqs.detail", rfq_id=rfq_id))
