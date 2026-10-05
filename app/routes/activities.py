import secrets

from flask import (
    Blueprint, abort, g, redirect, render_template, request, session, url_for,
)

from app.auth import module_required, roles_required
from app.workspace.services.commercial_activity_service import (
    CommercialActivityService,
)
from app.workspace.repositories.contact_repository import ActivityFormRepository
from app.workspace.repositories.activity_training_repository import (
    ActivityTrainingRepository,
)


activities_bp = Blueprint("activities", __name__, url_prefix="/activities")


@activities_bp.get("/")
@roles_required("administrator", "commercial_management", "advisor")
@module_required("activities")
def index():
    search = request.args.get("q", "").strip()
    return render_template(
        "activities/capture_index.html",
        customers=ActivityFormRepository.list_customers_for_capture(
            user=g.current_user, search=search
        ),
        search=search,
    )


@activities_bp.route("/training", methods=["GET", "POST"])
@roles_required("administrator", "commercial_management", "advisor")
@module_required("activities")
def training():
    if request.method == "POST":
        expected_token = session.pop("activity_training_token", None)
        if (
            not expected_token
            or not secrets.compare_digest(
                expected_token, request.form.get("completion_token", "")
            )
            or request.form.get("completed_steps") != "7"
        ):
            abort(400)
        ActivityTrainingRepository.complete(int(g.current_user["id"]))
        return redirect(url_for("activities.training", completed="1"))
    ActivityTrainingRepository.start(int(g.current_user["id"]))
    completion_token = secrets.token_urlsafe(24)
    session["activity_training_token"] = completion_token
    return render_template(
        "activities/training.html",
        completion=ActivityTrainingRepository.get(int(g.current_user["id"])),
        just_completed=request.args.get("completed") == "1",
        completion_token=completion_token,
    )


@activities_bp.get("/training/report")
@roles_required("administrator")
@module_required("activities")
def training_report():
    return render_template(
        "activities/training_report.html",
        rows=ActivityTrainingRepository.report(),
    )


@activities_bp.route("/customer/<int:customer_id>/new", methods=["GET", "POST"])
@roles_required("administrator", "commercial_management", "advisor")
@module_required("activities")
def new(customer_id: int):
    if not ActivityFormRepository.can_capture_customer(
        customer_id, user=g.current_user
    ):
        abort(403)
    error = None
    if request.method == "POST":
        try:
            result = CommercialActivityService.create(
                values={
                    **request.form.to_dict(),
                    "customer_id": customer_id,
                    "supplier_participated": bool(
                        request.form.get("supplier_participated")
                    ),
                    "participant_user_ids": request.form.getlist(
                        "participant_user_ids"
                    ),
                    "results": request.form.getlist("results"),
                    "advisor_user_id": (
                        g.current_user["id"]
                        if g.current_user["role"] == "advisor"
                        else request.form.get("advisor_user_id")
                    ),
                    "created_by": g.current_user["email"] or g.current_user["display_name"],
                    "created_by_user_id": g.current_user["id"],
                    "rollout_phase": "pilot",
                },
                evidence_files=request.files.getlist("evidence_files"),
            )
            return redirect(
                url_for(
                    "workspace.customer_detail",
                    customer_id=result.customer_id,
                )
            )
        except ValueError as exception:
            error = str(exception)
    return render_template(
        "activities/form.html",
        context=CommercialActivityService.form_context(customer_id),
        error=error,
        form=request.form,
    )


@activities_bp.route("/customer/<int:customer_id>/contacts", methods=["POST"])
@roles_required("administrator", "commercial_management", "advisor")
@module_required("activities")
def create_contact(customer_id: int):
    if not ActivityFormRepository.can_capture_customer(
        customer_id, user=g.current_user
    ):
        abort(403)
    CommercialActivityService.create_contact({
        **request.form.to_dict(),
        "customer_id": customer_id,
        "created_by_user_id": g.current_user["id"],
    })
    return redirect(
        url_for("activities.new", customer_id=customer_id)
    )
