from flask import Blueprint, render_template

from app.workspace.repositories.followup_repository import (
    FollowupRepository,
)
from app.workspace.repositories.project_repository import (
    ProjectRepository,
)
from app.workspace.services.workspace_dashboard_service import (
    WorkspaceDashboardService,
)

home_bp = Blueprint(
    "home",
    __name__,
)


@home_bp.route("/")
def home():
    dashboard = (
        WorkspaceDashboardService.get_dashboard()
    )

    return render_template(
        "home.html",
        dashboard=dashboard,
    )