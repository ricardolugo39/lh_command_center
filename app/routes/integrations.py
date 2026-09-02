from flask import Blueprint, current_app, g, redirect, render_template, session

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


@integrations_bp.get("/gmail/connect")
@roles_required("administrator")
def gmail_connect():
    provider = current_app.extensions["gmail_oauth_provider"]
    authorization_url, state, code_verifier = provider.authorization_url()
    session["gmail_oauth_state"] = state
    session["gmail_oauth_code_verifier"] = code_verifier
    session["gmail_oauth_user_id"] = g.current_user["id"]
    return redirect(authorization_url)
