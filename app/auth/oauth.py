import os
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

from flask import current_app, url_for
from google_auth_oauthlib.flow import Flow


class GoogleOAuthProvider:
    # Keep login scopes canonical and isolated from the separate Gmail flow.
    # Shorthand scopes plus include_granted_scopes caused Google to merge prior
    # Gmail grants and oauthlib correctly rejected the changed scope set.
    SCOPES = (
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    )

    def configured(self) -> bool:
        from app.auth.configuration import OAuthConfigurationService
        return OAuthConfigurationService.is_ready()

    def authorization_url(self) -> tuple[str, str, str]:
        flow = self._flow()
        authorization_url, state = flow.authorization_url(
            access_type="online", prompt="select_account",
        )
        if not flow.code_verifier:
            raise RuntimeError("Google OAuth no generó el verificador PKCE.")
        return authorization_url, state, flow.code_verifier

    def fetch_identity(
        self, authorization_response: str, *, code_verifier: str,
    ) -> dict[str, Any]:
        if not code_verifier:
            raise ValueError("Falta el verificador PKCE de OAuth.")
        flow = self._flow(code_verifier=code_verifier)
        with self._local_http_transport(authorization_response):
            flow.fetch_token(authorization_response=authorization_response)
        request = __import__("google.auth.transport.requests", fromlist=["Request"])
        id_token = __import__("google.oauth2.id_token", fromlist=["verify_oauth2_token"])
        claims = id_token.verify_oauth2_token(
            flow.credentials.id_token,
            request.Request(),
            current_app.config["GOOGLE_OAUTH_CLIENT_ID"],
        )
        return {
            "subject": claims["sub"], "email": claims["email"],
            "name": claims.get("name") or claims["email"],
            "email_verified": claims.get("email_verified", False),
        }

    @staticmethod
    @contextmanager
    def _local_http_transport(authorization_response: str):
        """Permit OAuth over HTTP only for a development loopback callback."""
        redirect_uri = str(
            current_app.config.get("GOOGLE_OAUTH_REDIRECT_URI") or ""
        ).strip()
        redirect = urlparse(redirect_uri)
        response = urlparse(authorization_response)
        is_development = (
            current_app.config.get("APP_ENVIRONMENT") == "development"
        )
        is_loopback = (
            redirect.scheme == "http"
            and response.scheme == "http"
            and redirect.hostname in {"127.0.0.1", "localhost", "::1"}
            and response.hostname == redirect.hostname
        )
        if not (is_development and is_loopback):
            yield
            return

        previous = os.environ.get("OAUTHLIB_INSECURE_TRANSPORT")
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)
            else:
                os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = previous

    def _flow(self, *, code_verifier: str | None = None) -> Flow:
        from app.auth.configuration import OAuthConfigurationService
        redirect_uri = OAuthConfigurationService.redirect_uri()
        return Flow.from_client_config(
            {
                "web": {
                    "client_id": current_app.config["GOOGLE_OAUTH_CLIENT_ID"],
                    "client_secret": current_app.config[
                        "GOOGLE_OAUTH_CLIENT_SECRET"
                    ],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=list(self.SCOPES),
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            autogenerate_code_verifier=code_verifier is None,
        )
