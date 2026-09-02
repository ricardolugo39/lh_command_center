from urllib.parse import urlsplit

from flask import (
    Blueprint, abort, current_app, g, redirect, render_template, request,
    session, url_for,
)
from oauthlib.oauth2 import OAuth2Error

from app.auth.configuration import OAuthConfigurationService
from app.auth.repository import UserRepository
from app.auth.service import AuthenticationService
from app.workspace.connectors.gmail_provider import GmailProvider
from app.workspace.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _safe_destination(value: str | None) -> str:
    if value and not urlsplit(value).netloc and value.startswith("/"):
        return value
    return url_for("home.home")


@auth_bp.get("/login")
def login():
    report = OAuthConfigurationService.report()
    return render_template(
        "auth/login.html",
        oauth_ready=report["enabled"],
        oauth_report=report,
        error=request.args.get("error"),
    )


@auth_bp.get("/status")
def status():
    user = getattr(g, "current_user", None)
    if user and user["role"] != "administrator":
        abort(403)
    return render_template(
        "auth/status.html", report=OAuthConfigurationService.report()
    )


@auth_bp.get("/google")
def google():
    provider = current_app.extensions["google_oauth_provider"]
    if not provider.configured():
        return redirect(url_for("auth.login", error="oauth_unavailable"))
    authorization_url, state, code_verifier = provider.authorization_url()
    session["oauth_state"] = state
    session["oauth_code_verifier"] = code_verifier
    session["post_login_next"] = _safe_destination(request.args.get("next"))
    return redirect(authorization_url)


@auth_bp.get("/callback")
def callback():
    gmail_state = session.get("gmail_oauth_state")
    if gmail_state:
        expected_state = session.pop("gmail_oauth_state", None)
        code_verifier = session.pop("gmail_oauth_code_verifier", None)
        expected_user_id = session.pop("gmail_oauth_user_id", None)
        if request.args.get("state") != expected_state:
            return redirect(url_for("integrations.index", gmail="failed"))
        if not g.current_user or g.current_user["id"] != expected_user_id:
            return redirect(url_for("auth.login", error="oauth_failed"))
        try:
            token = current_app.extensions[
                "gmail_oauth_provider"
            ].fetch_credentials(request.url, code_verifier=code_verifier)
            IntegrationCredentialRepository.save(
                GmailProvider.CREDENTIAL_KEY, token
            )
        except (KeyError, OAuth2Error, RuntimeError, ValueError, Warning):
            current_app.logger.exception("Gmail OAuth callback rejected")
            return redirect(url_for("integrations.index", gmail="failed"))
        return redirect(url_for("integrations.index", gmail="connected"))

    if request.args.get("state") != session.pop("oauth_state", None):
        session.pop("oauth_code_verifier", None)
        return redirect(url_for("auth.login", error="oauth_failed"))
    code_verifier = session.pop("oauth_code_verifier", None)
    try:
        identity = current_app.extensions[
            "google_oauth_provider"
        ].fetch_identity(request.url, code_verifier=code_verifier)
        user = AuthenticationService.authorize_google_identity(
            identity, current_app.config["GOOGLE_WORKSPACE_ALLOWED_DOMAIN"]
        )
    except (KeyError, OAuth2Error, RuntimeError, ValueError, Warning):
        current_app.logger.exception("Google OAuth callback rejected")
        return redirect(url_for("auth.login", error="oauth_failed"))
    destination = _safe_destination(session.get("post_login_next"))
    session.clear()
    session["user_id"] = user["id"]
    return redirect(destination)


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.post("/development-login")
def development_login():
    if not OAuthConfigurationService.development_login_available():
        abort(404)
    user = UserRepository.first_active()
    if not user or user["role"] != "administrator":
        abort(403)
    session.clear()
    session["user_id"] = user["id"]
    return redirect(url_for("home.home"))
