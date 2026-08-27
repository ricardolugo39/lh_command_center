from functools import wraps
from typing import Any, Callable, TypeVar, cast

from flask import (
    Flask, abort, current_app, g, redirect, request, session, url_for,
)

from app.auth.oauth import GoogleOAuthProvider
from app.auth.repository import UserRepository
from app.auth.routes import auth_bp


Result = TypeVar("Result")
ROLE_LABELS = {
    "administrator": "Administrador",
    "commercial_management": "Gerencia Comercial",
    "advisor": "Asesor Comercial",
    "read_only": "Consulta",
}


def init_auth(application: Flask, provider: Any | None = None) -> None:
    application.register_blueprint(auth_bp)
    application.extensions["google_oauth_provider"] = (
        provider or GoogleOAuthProvider()
    )

    @application.before_request
    def load_and_protect():
        g.current_user = None
        if application.testing and application.config.get("TEST_AUTH_BYPASS"):
            user_id = application.config.get("TEST_AUTH_USER_ID")
            g.current_user = (
                UserRepository.get(user_id) if user_id
                else UserRepository.first_active()
            )
            return None
        user_id = session.get("user_id")
        if user_id:
            user = UserRepository.get(int(user_id))
            if user and user["is_active"]:
                g.current_user = user
        if (
            request.blueprint == "auth"
            or request.endpoint in {"static", "home.healthcheck"}
        ):
            return None
        if not g.current_user:
            return redirect(url_for("auth.login", next=request.full_path))
        return None

    application.context_processor(
        lambda: {
            "current_user": getattr(g, "current_user", None),
            "role_labels": ROLE_LABELS,
        }
    )


def roles_required(*roles: str):
    def decorator(function: Callable[..., Result]) -> Callable[..., Result]:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Result:
            if "google_oauth_provider" not in current_app.extensions:
                return function(*args, **kwargs)
            user = getattr(g, "current_user", None)
            if not user or user["role"] not in roles:
                abort(403)
            return function(*args, **kwargs)
        return cast(Callable[..., Result], wrapped)
    return decorator
