from pathlib import Path

from flask import Blueprint, abort, g, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from app.auth import roles_required
from app.storage import upload_path
from app.workspace.repositories.quote_management_repository import QuoteManagementRepository
from app.workspace.services.quote_management_service import QuoteManagementService, QUOTE_STATUSES
from app.workspace.constants.commercial_office import OFFICES


quotes_bp = Blueprint("quotes", __name__, url_prefix="/quotes")


@quotes_bp.get("/")
@roles_required("administrator", "commercial_management", "advisor", "read_only")
def index():
    filters = request.args.to_dict()
    if filters.get("office") not in OFFICES:
        filters["office"] = ""
    return render_template(
        "quotes/index.html", quotes=QuoteManagementRepository.portfolio(filters),
        filters=filters, statuses=QUOTE_STATUSES, offices=OFFICES,
    )


@quotes_bp.route("/<int:quote_id>", methods=["GET", "POST"])
@roles_required("administrator")
def workspace(quote_id: int):
    error = None
    if request.method == "POST":
        try:
            ids = request.form.getlist("line_id")
            values = []
            fields = (
                "vendor_fob_unit_usd", "unit_weight_kg", "lead_time",
                "pricing_rule_id", "pricing_override_value",
                "pricing_override_reason", "internal_notes",
            )
            lists = {field: request.form.getlist(field) for field in fields}
            for index, raw_id in enumerate(ids):
                values.append({
                    "id": int(raw_id),
                    **{field: lists[field][index] if index < len(lists[field]) else "" for field in fields},
                })
            QuoteManagementService.save_workspace(
                quote_id, request.form.to_dict(), values, g.current_user["id"]
            )
            if request.form.get("action") == "calculate":
                QuoteManagementService.calculate(quote_id)
            return redirect(url_for("quotes.workspace", quote_id=quote_id))
        except (TypeError, ValueError) as exception:
            error = str(exception)
    try:
        page = QuoteManagementService.workspace(quote_id)
    except ValueError:
        abort(404)
    return render_template("quotes/workspace.html", page=page, error=error)


@quotes_bp.post("/<int:quote_id>/revision")
@roles_required("administrator")
def revision(quote_id: int):
    try:
        new_id = QuoteManagementService.new_revision(quote_id, g.current_user["id"])
    except ValueError as exception:
        return str(exception), 400
    return redirect(url_for("quotes.workspace", quote_id=new_id))


@quotes_bp.post("/<int:quote_id>/delete")
@roles_required("administrator")
def delete(quote_id: int):
    try:
        project_id = QuoteManagementService.delete_draft(quote_id)
    except ValueError as exception:
        return str(exception), 400
    if project_id:
        return redirect(url_for("workspace.project_detail", project_id=project_id))
    return redirect(url_for("quotes.index"))


@quotes_bp.post("/<int:quote_id>/generate-pdf")
@roles_required("administrator")
def generate_pdf(quote_id: int):
    try:
        QuoteManagementService.generate_pdf(quote_id, g.current_user["id"])
    except ValueError as exception:
        return render_template(
            "quotes/workspace.html", page=QuoteManagementService.workspace(quote_id),
            error=str(exception),
        ), 400
    return redirect(url_for("quotes.delivery", quote_id=quote_id))


@quotes_bp.get("/<int:quote_id>/pdf")
@roles_required("administrator", "commercial_management", "advisor", "read_only")
def pdf(quote_id: int):
    artifact = QuoteManagementRepository.latest_pdf(quote_id)
    if not artifact or not Path(artifact["stored_filename"]).is_file():
        abort(404)
    return send_file(Path(artifact["stored_filename"]).resolve(), mimetype="application/pdf")


@quotes_bp.route("/<int:quote_id>/delivery", methods=["GET", "POST"])
@roles_required("administrator")
def delivery(quote_id: int):
    if request.method == "POST":
        review = request.form.to_dict()
        review["attachment_ids"] = request.form.getlist("attachment_ids")
        QuoteManagementService.prepare_delivery(quote_id, g.current_user["id"], review)
        return redirect(url_for("quotes.delivery", quote_id=quote_id))
    page = QuoteManagementService.workspace(quote_id)
    page["delivery"] = QuoteManagementRepository.latest_delivery(quote_id)
    return render_template("quotes/delivery.html", page=page)


@quotes_bp.post("/<int:quote_id>/attachments")
@roles_required("administrator")
def upload_attachment(quote_id: int):
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return "Seleccione un archivo.", 400
    safe_name = secure_filename(upload.filename)
    root = upload_path("quotes", str(quote_id))
    root.mkdir(parents=True, exist_ok=True)
    path = root / safe_name
    upload.save(path)
    QuoteManagementRepository.add_attachment(quote_id, {
        "original_filename": upload.filename, "stored_filename": str(path),
        "mime_type": upload.mimetype, "size_bytes": path.stat().st_size,
        "category": request.form.get("category") or "other",
        "uploaded_by_user_id": g.current_user["id"],
        "vendor_confidential": bool(request.form.get("vendor_confidential")),
    })
    return redirect(url_for("quotes.workspace", quote_id=quote_id))


@quotes_bp.post("/deliveries/<int:delivery_id>/send")
@roles_required("administrator")
def send_delivery(delivery_id: int):
    delivery_record = QuoteManagementRepository.get_delivery(delivery_id)
    if not delivery_record:
        abort(404)
    try:
        QuoteManagementService.send_delivery(delivery_id, g.current_user["id"])
    except ValueError as exception:
        return str(exception), 400
    return redirect(url_for("quotes.delivery", quote_id=delivery_record["quote_id"]))


@quotes_bp.post("/<int:quote_id>/outcome")
@roles_required("administrator")
def outcome(quote_id: int):
    try:
        QuoteManagementService.record_outcome(
            quote_id, request.form.to_dict(), g.current_user["id"]
        )
    except ValueError as exception:
        return str(exception), 400
    return redirect(url_for("quotes.workspace", quote_id=quote_id))
