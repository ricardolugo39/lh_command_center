from flask import Blueprint, current_app, redirect, render_template, request, url_for

from app.workspace.services.commercial_activity_service import (
    CommercialActivityService,
)


activities_bp = Blueprint("activities", __name__, url_prefix="/activities")


@activities_bp.route("/customer/<int:customer_id>/new", methods=["GET", "POST"])
def new(customer_id: int):
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
                    "created_by": current_app.config.get(
                        "CURRENT_USER", "system"
                    ),
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
def create_contact(customer_id: int):
    CommercialActivityService.create_contact({
        **request.form.to_dict(),
        "customer_id": customer_id,
    })
    return redirect(
        url_for("activities.new", customer_id=customer_id)
    )
