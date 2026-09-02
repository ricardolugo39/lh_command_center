from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, url_for

from app.database.connection import get_connection

from app.workspace.repositories.advisor_review_repository import AdvisorReviewRepository
from app.workspace.repositories.commercial_visit_repository import CommercialVisitRepository
from app.workspace.services.advisor_management_service import AdvisorManagementService
from app.workspace.services.advisor_monthly_report_service import (
    AdvisorMonthlyReportService,
)
from app.workspace.services.manager_home_service import ManagerHomeService
from app.workspace.services.workspace_dashboard_service import (
    WorkspaceDashboardService,
)
from app.workspace.services.project_workspace_service import ProjectWorkspaceService

home_bp = Blueprint(
    "home",
    __name__,
)


@home_bp.get("/healthz")
def healthcheck():
    with get_connection() as connection:
        connection.execute("SELECT 1").fetchone()
    return jsonify(status="ok")


@home_bp.route("/")
def home():
    office = str(current_app.config.get("DEFAULT_COMMERCIAL_OFFICE", "Cali"))
    dashboard = ManagerHomeService.get_page(office)

    return render_template(
        "home.html",
        dashboard=dashboard,
    )


@home_bp.route("/activities")
def activities():
    office = str(current_app.config.get("DEFAULT_COMMERCIAL_OFFICE", "Cali"))
    dashboard = WorkspaceDashboardService.get_dashboard(office)
    return render_template("activities/index.html", dashboard=dashboard, office=office)


@home_bp.post("/activities/visits/<int:followup_id>/complete")
def complete_visit_activity(followup_id: int):
    try:
        CommercialVisitRepository.complete_followup(followup_id)
    except ValueError:
        abort(404)
    return redirect(url_for("home.activities"))


@home_bp.post("/activities/opportunities/<int:followup_id>/complete")
def complete_opportunity_activity(followup_id: int):
    try:
        ProjectWorkspaceService.complete_followup(followup_id=followup_id)
    except ValueError:
        abort(404)
    return redirect(url_for("home.activities"))


@home_bp.post("/activities/visits/<int:followup_id>/reschedule")
def reschedule_visit_activity(followup_id: int):
    try:
        CommercialVisitRepository.reschedule_followup(
            followup_id, request.form.get("due_date", ""),
            request.form.get("reason", ""),
        )
    except ValueError as exc:
        return str(exc), 400
    return redirect(url_for("home.activities"))


@home_bp.get("/team/<path:advisor_name>")
def advisor_management(advisor_name: str):
    office = str(current_app.config.get("DEFAULT_COMMERCIAL_OFFICE", "Cali"))
    page = AdvisorManagementService.get_page(
        advisor_name, office, request.args.get("period", "week")
    )
    return render_template("team/advisor_management.html", page=page)


@home_bp.get("/team/<path:advisor_name>/report")
def advisor_monthly_report(advisor_name: str):
    office = str(current_app.config.get("DEFAULT_COMMERCIAL_OFFICE", "Cali"))
    try:
        page = AdvisorMonthlyReportService.get_page(
            advisor_name, office, request.args.get("month", "2026-08")
        )
    except ValueError as exc:
        return str(exc), 400
    return render_template("team/advisor_monthly_report.html", page=page)


@home_bp.post("/team/<path:advisor_name>/reviews")
def schedule_advisor_review(advisor_name: str):
    scheduled_at = request.form.get("scheduled_at", "").strip()
    if not scheduled_at:
        return "La fecha de la revisión es obligatoria.", 400
    AdvisorReviewRepository.create(
        advisor_name=advisor_name, scheduled_at=scheduled_at,
        period_start=request.form.get("period_start") or None,
        period_end=request.form.get("period_end") or None,
        created_by="manager",
    )
    return redirect(url_for("home.advisor_management", advisor_name=advisor_name))


@home_bp.post("/team/<path:advisor_name>/reviews/<int:review_id>/complete")
def complete_advisor_review(advisor_name: str, review_id: int):
    try:
        AdvisorReviewRepository.complete(review_id, request.form.get("notes", ""))
    except ValueError as exc:
        return str(exc), 400
    return redirect(url_for("home.advisor_management", advisor_name=advisor_name))
