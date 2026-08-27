from flask import (
    Blueprint, abort, current_app, redirect, render_template, request, url_for,
)

from app.workspace.services.erp_import_service import (
    ERPImportService,
    ERPImportValidationError,
)
from app.auth import roles_required
from app.workspace.repositories.customer_repository import CustomerRepository
from app.workspace.repositories.opportunity_import_repository import (
    OpportunityImportRepository,
)
from app.workspace.services.opportunity_import_profile_service import (
    OpportunityImportProfileService,
)
from app.workspace.services.opportunity_import_service import (
    OpportunityImportService,
    OpportunityImportValidationError,
)


imports_bp = Blueprint("imports", __name__, url_prefix="/imports")


@imports_bp.route("/", methods=["GET"])
@roles_required("administrator")
def index():
    return render_template(
        "imports/index.html",
        executions=ERPImportService.history(),
        opportunity_profile=OpportunityImportProfileService.active_profile(),
        pending_opportunity_count=len(
            OpportunityImportService.pending_queue()
        ),
        error=None,
    )


@imports_bp.route("/preview", methods=["POST"])
@roles_required("administrator")
def preview():
    try:
        preview_data = ERPImportService.prepare(
            import_type=request.form.get("import_type", ""),
            upload=request.files.get("file"),
            executed_by=current_app.config.get("CURRENT_USER", "system"),
            snapshot_date=request.form.get("snapshot_date"),
        )
    except ERPImportValidationError as error:
        return render_template(
            "imports/index.html",
            executions=ERPImportService.history(),
            opportunity_profile=OpportunityImportProfileService.active_profile(),
            pending_opportunity_count=len(
                OpportunityImportService.pending_queue()
            ),
            error=str(error),
        ), 400
    return render_template("imports/preview.html", preview=preview_data)


@imports_bp.route("/<int:execution_id>/confirm", methods=["POST"])
@roles_required("administrator")
def confirm(execution_id: int):
    try:
        ERPImportService.confirm(
            execution_id,
            overwrite_existing=request.form.get("overwrite_existing") == "1",
        )
    except ERPImportValidationError as error:
        return render_template(
            "imports/detail.html",
            execution=ERPImportService.detail(execution_id),
            error=str(error),
        ), 400
    return redirect(url_for("imports.detail", execution_id=execution_id))


@imports_bp.route("/<int:execution_id>", methods=["GET"])
@roles_required("administrator")
def detail(execution_id: int):
    execution = ERPImportService.detail(execution_id)
    if not execution:
        abort(404)
    return render_template(
        "imports/detail.html", execution=execution, error=None
    )


@imports_bp.route("/crm-opportunities/preview", methods=["POST"])
@roles_required("administrator")
def opportunity_preview():
    try:
        preview_data = OpportunityImportService.prepare(
            upload=request.files.get("file"),
            executed_by=current_app.config.get("CURRENT_USER", "system"),
        )
    except OpportunityImportValidationError as error:
        return render_template(
            "imports/index.html",
            executions=ERPImportService.history(),
            opportunity_profile=OpportunityImportProfileService.active_profile(),
            error=str(error),
        ), 400
    return render_template(
        "imports/opportunity_preview.html",
        preview=preview_data,
        customers=CustomerRepository.list_customers(),
        sellers=OpportunityImportRepository.seller_candidates(),
        error=None,
    )


@imports_bp.route(
    "/crm-opportunities/<int:execution_id>/resolve-customer",
    methods=["POST"],
)
@roles_required("administrator")
def opportunity_resolve_customer(execution_id: int):
    try:
        preview_data = OpportunityImportService.resolve_customer(
            execution_id,
            request.form.get("external_opportunity_id", ""),
            customer_id=int(request.form.get("customer_id", "")),
            resolved_by=current_app.config.get("CURRENT_USER", "system"),
        )
    except (OpportunityImportValidationError, ValueError) as error:
        preview_data = OpportunityImportService.preview(execution_id)
        return render_template(
            "imports/opportunity_preview.html",
            preview=preview_data,
            customers=CustomerRepository.list_customers(),
            sellers=OpportunityImportRepository.seller_candidates(),
            error=str(error),
        ), 400
    return render_template(
        "imports/opportunity_preview.html",
        preview=preview_data,
        customers=CustomerRepository.list_customers(),
        sellers=OpportunityImportRepository.seller_candidates(),
        error=None,
    )


@imports_bp.route(
    "/crm-opportunities/<int:execution_id>/confirm", methods=["POST"]
)
@roles_required("administrator")
def opportunity_confirm(execution_id: int):
    try:
        OpportunityImportService.confirm(
            execution_id,
            confirmed=request.form.get("confirmed") == "1",
            executed_by=current_app.config.get("CURRENT_USER", "system"),
        )
    except OpportunityImportValidationError as error:
        return render_template(
            "imports/opportunity_preview.html",
            preview=OpportunityImportService.preview(execution_id),
            customers=CustomerRepository.list_customers(),
            sellers=OpportunityImportRepository.seller_candidates(),
            error=str(error),
        ), 400
    return redirect(url_for("imports.detail", execution_id=execution_id))


@imports_bp.route(
    "/crm-opportunities/<int:execution_id>/resolve-seller",
    methods=["POST"],
)
@roles_required("administrator")
def opportunity_resolve_seller(execution_id: int):
    try:
        preview_data = OpportunityImportService.resolve_seller(
            execution_id,
            request.form.get("external_opportunity_id", ""),
            sales_rep=request.form.get("sales_rep", ""),
            resolved_by=current_app.config.get("CURRENT_USER", "system"),
        )
    except OpportunityImportValidationError as error:
        preview_data = OpportunityImportService.preview(execution_id)
        return render_template(
            "imports/opportunity_preview.html",
            preview=preview_data,
            customers=CustomerRepository.list_customers(),
            sellers=OpportunityImportRepository.seller_candidates(),
            error=str(error),
        ), 400
    return render_template(
        "imports/opportunity_preview.html",
        preview=preview_data,
        customers=CustomerRepository.list_customers(),
        sellers=OpportunityImportRepository.seller_candidates(),
        error=None,
    )


@imports_bp.route("/crm-opportunities/pending", methods=["GET"])
@roles_required("administrator")
def opportunity_pending():
    return render_template(
        "imports/opportunity_pending.html",
        pending=OpportunityImportService.pending_queue(),
        customers=CustomerRepository.list_customers(),
        error=None,
    )


@imports_bp.route(
    "/crm-opportunities/pending/<int:pending_id>/resolve",
    methods=["POST"],
)
@roles_required("administrator")
def opportunity_pending_resolve(pending_id: int):
    try:
        OpportunityImportService.resolve_pending_customer(
            pending_id,
            customer_id=int(request.form.get("customer_id", "")),
            apply_to_company=request.form.get("apply_scope") == "company",
            resolved_by=current_app.config.get("CURRENT_USER", "system"),
        )
    except (OpportunityImportValidationError, ValueError) as error:
        return render_template(
            "imports/opportunity_pending.html",
            pending=OpportunityImportService.pending_queue(),
            customers=CustomerRepository.list_customers(),
            error=str(error),
        ), 400
    return redirect(url_for("imports.opportunity_pending"))


@imports_bp.route(
    "/crm-opportunities/pending/import", methods=["POST"]
)
@roles_required("administrator")
def opportunity_pending_import():
    selected = [
        int(value) for value in request.form.getlist("pending_id")
        if str(value).isdigit()
    ]
    try:
        result = OpportunityImportService.import_resolved_pending(
            pending_ids=selected or None,
            executed_by=current_app.config.get("CURRENT_USER", "system"),
        )
    except OpportunityImportValidationError as error:
        return render_template(
            "imports/opportunity_pending.html",
            pending=OpportunityImportService.pending_queue(),
            customers=CustomerRepository.list_customers(),
            error=str(error),
        ), 400
    return redirect(
        url_for(
            "imports.detail",
            execution_id=result["execution_ids"][-1],
        )
    )
