from flask import (
    Blueprint, current_app, g, redirect, render_template, request, session,
    url_for,
)

from app.workspace.services.integration_center_service import (
    IntegrationCenterService,
)
from app.auth import roles_required
from app.auth.service import AuthenticationService


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


@integrations_bp.get("/microsoft-mail/connect")
@roles_required("administrator")
def microsoft_mail_connect():
    try:
        flow = current_app.extensions[
            "microsoft_mail_oauth_provider"
        ].begin()
    except RuntimeError:
        current_app.logger.exception("Microsoft mail OAuth is unavailable")
        return redirect(url_for("integrations.index", microsoft_mail="failed"))
    session["microsoft_mail_oauth_flow"] = flow
    session["microsoft_mail_oauth_user_id"] = g.current_user["id"]
    return redirect(flow["auth_uri"])


@integrations_bp.get("/microsoft-mail/callback")
def microsoft_mail_callback():
    login_flow = session.pop("microsoft_login_flow", None)
    if login_flow:
        try:
            identity = current_app.extensions[
                "microsoft_mail_oauth_provider"
            ].complete_login(login_flow, request.args.to_dict(flat=True))
            user = AuthenticationService.authorize_microsoft_identity(
                identity,
                allowed_domain=current_app.config[
                    "GOOGLE_WORKSPACE_ALLOWED_DOMAIN"
                ],
                tenant_id=current_app.config["MICROSOFT_TENANT_ID"],
            )
        except (KeyError, RuntimeError, ValueError):
            current_app.logger.exception("Microsoft login callback rejected")
            return redirect(url_for("auth.login", error="oauth_failed"))
        destination = session.get("post_login_next")
        session.clear()
        session["user_id"] = user["id"]
        return redirect(destination or url_for("home.home"))

    flow = session.pop("microsoft_mail_oauth_flow", None)
    expected_user_id = session.pop("microsoft_mail_oauth_user_id", None)
    if (
        not flow
        or not g.current_user
        or g.current_user["role"] != "administrator"
        or g.current_user["id"] != expected_user_id
    ):
        return redirect(url_for("integrations.index", microsoft_mail="failed"))
    try:
        current_app.extensions["microsoft_mail_oauth_provider"].complete(
            flow, request.args.to_dict(flat=True)
        )
    except (KeyError, RuntimeError, ValueError):
        current_app.logger.exception("Microsoft mail OAuth callback rejected")
        return redirect(url_for("integrations.index", microsoft_mail="failed"))
    return redirect(url_for("integrations.index", microsoft_mail="connected"))
