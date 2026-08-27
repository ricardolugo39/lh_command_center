from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import current_app, has_request_context, url_for


OAUTH_VARIABLES = (
    "FLASK_SECRET_KEY",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REDIRECT_URI",
    "GOOGLE_WORKSPACE_ALLOWED_DOMAIN",
)


@dataclass(frozen=True)
class ConfigurationItem:
    name: str
    label: str
    configured: bool
    display_value: str
    source: str
    expected_format: str
    validation_error: str | None = None


class OAuthConfigurationService:
    LABELS = {
        "GOOGLE_OAUTH_CLIENT_ID": "Client ID",
        "GOOGLE_OAUTH_CLIENT_SECRET": "Client Secret",
        "GOOGLE_OAUTH_REDIRECT_URI": "Redirect URI",
        "GOOGLE_WORKSPACE_ALLOWED_DOMAIN": "Dominio de Google Workspace",
        "FLASK_SECRET_KEY": "Flask Secret Key",
    }
    FORMATS = {
        "GOOGLE_OAUTH_CLIENT_ID":
            "Identificador OAuth Web terminado en .apps.googleusercontent.com",
        "GOOGLE_OAUTH_CLIENT_SECRET":
            "Secreto del cliente OAuth Web generado por Google Cloud",
        "GOOGLE_OAUTH_REDIRECT_URI":
            "URL absoluta HTTPS en producción, terminada en /auth/callback",
        "GOOGLE_WORKSPACE_ALLOWED_DOMAIN":
            "Dominio sin @, por ejemplo lugohermanos.com",
        "FLASK_SECRET_KEY":
            "Cadena aleatoria de al menos 32 bytes; no debe compartirse",
    }

    @classmethod
    def report(cls) -> dict[str, Any]:
        items = tuple(cls._item(name) for name in OAUTH_VARIABLES)
        missing = tuple(
            item for item in items
            if not item.configured and item.name != "GOOGLE_OAUTH_REDIRECT_URI"
        )
        invalid = tuple(
            item for item in items
            if item.configured and item.validation_error
        )
        return {
            "enabled": not missing and not invalid,
            "items": items,
            "missing": missing,
            "invalid": invalid,
            "expected_redirect_uri": cls.redirect_uri(),
            "environment": current_app.config.get(
                "APP_ENVIRONMENT", "production"
            ),
            "development_login_available": cls.development_login_available(),
        }

    @staticmethod
    def development_login_available() -> bool:
        return (
            current_app.config.get("APP_ENVIRONMENT") == "development"
            and not OAuthConfigurationService.is_ready()
        )

    @classmethod
    def is_ready(cls) -> bool:
        items = tuple(cls._item(name) for name in OAUTH_VARIABLES)
        return all(
            item.configured and not item.validation_error
            for item in items
            if item.name != "GOOGLE_OAUTH_REDIRECT_URI"
        )

    @staticmethod
    def redirect_uri() -> str:
        configured = str(
            current_app.config.get("GOOGLE_OAUTH_REDIRECT_URI") or ""
        ).strip()
        if configured:
            return configured
        if has_request_context():
            return url_for("auth.callback", _external=True)
        return "/auth/callback"

    @classmethod
    def _item(cls, name: str) -> ConfigurationItem:
        value = (
            current_app.secret_key if name == "FLASK_SECRET_KEY"
            else current_app.config.get(name)
        )
        clean = str(value or "").strip()
        provenance = current_app.extensions.get(
            "oauth_configuration_sources", {}
        )
        source = provenance.get(name, "Missing")
        configured = bool(clean)
        if name == "GOOGLE_OAUTH_REDIRECT_URI" and not clean:
            clean = cls.redirect_uri()
            source = "Default value"
            configured = True
        if name == "GOOGLE_WORKSPACE_ALLOWED_DOMAIN" and clean:
            source = provenance.get(name, "Default value")
        if not configured:
            display = "No configurado"
        elif "SECRET" in name or name == "FLASK_SECRET_KEY":
            display = "••••••••"
        elif name == "GOOGLE_OAUTH_CLIENT_ID":
            display = cls._mask(clean)
        else:
            display = clean
        return ConfigurationItem(
            name=name, label=cls.LABELS[name], configured=configured,
            display_value=display, source=source,
            expected_format=cls.FORMATS[name],
            validation_error=cls._validation_error(name, clean, configured),
        )

    @staticmethod
    def _validation_error(
        name: str, value: str, configured: bool
    ) -> str | None:
        if not configured:
            return None
        if name == "FLASK_SECRET_KEY" and len(value) < 32:
            return "Debe contener al menos 32 caracteres."
        if (
            name == "GOOGLE_OAUTH_CLIENT_ID"
            and not value.endswith(".apps.googleusercontent.com")
        ):
            return "No tiene el formato de Client ID OAuth de Google."
        if (
            name == "GOOGLE_WORKSPACE_ALLOWED_DOMAIN"
            and ("@" in value or "." not in value)
        ):
            return "Debe ser un dominio sin @."
        return None

    @staticmethod
    def _mask(value: str) -> str:
        if len(value) < 16:
            return "••••••••"
        return f"{value[:8]}…{value[-12:]}"


def source_label(source: Path | None, *, project_env: Path, legacy_env: Path,
                 project_config: Path) -> str:
    if source is None:
        return "Operating System Environment"
    resolved = source.resolve()
    if resolved == project_env.resolve():
        return ".env"
    if resolved == legacy_env.resolve():
        return "Legacy .env"
    if resolved == project_config.resolve():
        return "Flask config"
    return f".env ({resolved})"
