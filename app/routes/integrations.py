from flask import Blueprint, render_template

from app.workspace.services.integration_center_service import (
    IntegrationCenterService,
)
from app.auth import roles_required


integrations_bp = Blueprint(
    "integrations", __name__, url_prefix="/integrations"
)


@integrations_bp.get("/")
@roles_required("administrator")
def index():
    return render_template(
        "integrations/index.html",
        page=IntegrationCenterService.get_page(),
    )
