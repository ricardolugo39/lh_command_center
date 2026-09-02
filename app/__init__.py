import secrets

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.auth import init_auth
from app.auth.oauth import GmailOAuthProvider
from app.auth.configuration import OAUTH_VARIABLES, source_label
from app.configuration import (
    LEGACY_ENV_PATH, PROJECT_CONFIG_PATH, PROJECT_ENV_PATH, resolve_settings,
)
from app.workspace.connectors.gmail_provider import GmailProvider
from app.database.migrations import MigrationReport, upgrade
from app.routes import register_blueprints
from app.routes.api.customers import customers_api


def create_app(
    config: dict | None = None, *, run_migrations: bool = True,
    oauth_provider=None, gmail_provider=None,
) -> Flask:
    """Create an application that is schema-ready before serving requests."""
    application = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    application.wsgi_app = ProxyFix(
        application.wsgi_app, x_for=1, x_proto=1, x_host=1
    )
    settings, setting_sources = resolve_settings(
        OAUTH_VARIABLES + ("FLASK_ENV", "DEFAULT_COMMERCIAL_OFFICE")
    )
    provenance = {
        name: source_label(
            source, project_env=PROJECT_ENV_PATH,
            legacy_env=LEGACY_ENV_PATH, project_config=PROJECT_CONFIG_PATH,
        )
        for name, source in setting_sources.items()
    }
    application.config.update(
        SECRET_KEY=settings.get("FLASK_SECRET_KEY"),
        GOOGLE_OAUTH_CLIENT_ID=settings.get("GOOGLE_OAUTH_CLIENT_ID"),
        GOOGLE_OAUTH_CLIENT_SECRET=settings.get("GOOGLE_OAUTH_CLIENT_SECRET"),
        GOOGLE_OAUTH_REDIRECT_URI=settings.get("GOOGLE_OAUTH_REDIRECT_URI"),
        GOOGLE_WORKSPACE_ALLOWED_DOMAIN=settings.get(
            "GOOGLE_WORKSPACE_ALLOWED_DOMAIN", "lugohermanos.com"
        ),
        APP_ENVIRONMENT=settings.get("FLASK_ENV", "production").casefold(),
        DEFAULT_COMMERCIAL_OFFICE=settings.get(
            "DEFAULT_COMMERCIAL_OFFICE", "Cali"
        ),
    )
    if config:
        application.config.update(config)
        if config.get("FLASK_ENV"):
            application.config["APP_ENVIRONMENT"] = str(
                config["FLASK_ENV"]
            ).casefold()
        for name in OAUTH_VARIABLES:
            config_name = "SECRET_KEY" if name == "FLASK_SECRET_KEY" else name
            if config.get(config_name):
                provenance[name] = "Flask config"
    if (
        application.config["APP_ENVIRONMENT"] == "development"
        and not application.secret_key
    ):
        application.secret_key = secrets.token_urlsafe(48)
        provenance["FLASK_SECRET_KEY"] = "Default value (development only)"
    if application.testing and not application.secret_key:
        application.secret_key = "test-only-secret"

    migration_report: MigrationReport | None = None
    if run_migrations:
        migration_report = upgrade()

    register_blueprints(application)
    application.register_blueprint(customers_api)
    init_auth(application, oauth_provider)
    application.extensions["oauth_configuration_sources"] = provenance
    application.extensions["gmail_provider"] = gmail_provider or GmailProvider()
    application.extensions["gmail_oauth_provider"] = GmailOAuthProvider()
    application.extensions["schema_migration_report"] = migration_report

    if migration_report:
        for warning in migration_report.warnings:
            application.logger.warning("Migración: %s", warning)

    with application.app_context():
        from app.auth.configuration import OAuthConfigurationService
        report = OAuthConfigurationService.report()
        application.extensions["oauth_configuration_report"] = report
        if not report["enabled"]:
            problems = (
                [item.name for item in report["missing"]]
                + [
                    f"{item.name} ({item.validation_error})"
                    for item in report["invalid"]
                ]
            )
            application.logger.warning(
                "Google OAuth incompleto: %s. Consulte /auth/status.",
                ", ".join(problems),
            )

    if not application.testing and application.config["APP_ENVIRONMENT"] == "production":
        from app.workspace.stock_planning.scheduler import (
            start_stock_replenishment_scheduler,
        )
        start_stock_replenishment_scheduler()

    return application
