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
        user_id = None
        if application.testing and application.config.get("TEST_AUTH_BYPASS"):
            user_id = application.config.get("TEST_AUTH_USER_ID")
            user = (
                UserRepository.get(user_id) if user_id
                else UserRepository.first_active()
            )
            if user:
                user = dict(user)
                user["enabled_modules"] = UserRepository.enabled_modules(
                    int(user["id"])
                )
                g.current_user = user
        else:
            user_id = session.get("user_id")
        if not g.current_user and user_id:
            user = UserRepository.get(int(user_id))
            if user and user["is_active"]:
                user = dict(user)
                user["enabled_modules"] = UserRepository.enabled_modules(
                    int(user["id"])
                )
                g.current_user = user
        if (
            request.blueprint == "auth"
            or request.endpoint == "integrations.microsoft_mail_callback"
            or request.endpoint in {"static", "home.healthcheck"}
        ):
            return None
        if not g.current_user:
            return redirect(url_for("auth.login", next=request.full_path))
        if (
            g.current_user.get("module_access_mode") == "limited"
            and request.endpoint not in {
                "static", "home.healthcheck", "auth.logout",
            }
            and request.blueprint != "activities"
        ):
            if request.endpoint == "home.home":
                return redirect(url_for("activities.index"))
            abort(403)
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


def module_required(module_key: str):
    """Require a module entitlement for limited users.

    Full-access users retain their existing permissions. This lets production
    pilot accounts receive only Activity Capture without changing established
    manager and administrator access.
    """
    def decorator(function: Callable[..., Result]) -> Callable[..., Result]:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Result:
            user = getattr(g, "current_user", None)
            if not user:
                abort(403)
            if user.get("module_access_mode") == "limited" and module_key not in (
                user.get("enabled_modules") or set()
            ):
                abort(403)
            return function(*args, **kwargs)
        return cast(Callable[..., Result], wrapped)
    return decorator
