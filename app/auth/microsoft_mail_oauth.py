from typing import Any

from flask import current_app
from msal import ConfidentialClientApplication, SerializableTokenCache

from app.workspace.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)

MICROSOFT_MAIL_VARIABLES = (
    "MICROSOFT_TENANT_ID",
    "MICROSOFT_CLIENT_ID",
    "MICROSOFT_CLIENT_SECRET",
    "MICROSOFT_MAIL_REDIRECT_URI",
    "MICROSOFT_MAILBOX_ADDRESS",
)


class MicrosoftMailOAuthProvider:
    """Delegated Microsoft Graph authorization for the operational mailbox."""

    CREDENTIAL_KEY = "microsoft_mail_token_cache"
    SCOPES = ("Mail.ReadWrite", "Mail.Send")
    LOGIN_SCOPES = ("User.Read",)

    @classmethod
    def configured(cls) -> bool:
        return all(
            str(current_app.config.get(name) or "").strip()
            for name in (
                "MICROSOFT_TENANT_ID",
                "MICROSOFT_CLIENT_ID",
                "MICROSOFT_CLIENT_SECRET",
                "MICROSOFT_MAIL_REDIRECT_URI",
            )
        )

    def begin(self) -> dict[str, Any]:
        if not self.configured():
            raise RuntimeError("La integración de Microsoft 365 no está configurada.")
        return self._client()[0].initiate_auth_code_flow(
            scopes=list(self.SCOPES),
            redirect_uri=current_app.config["MICROSOFT_MAIL_REDIRECT_URI"],
            prompt="select_account",
        )

    def begin_login(self) -> dict[str, Any]:
        if not self.configured():
            raise RuntimeError("El inicio de sesión de Microsoft no está configurado.")
        return self._client()[0].initiate_auth_code_flow(
            scopes=list(self.LOGIN_SCOPES),
            redirect_uri=current_app.config["MICROSOFT_MAIL_REDIRECT_URI"],
            prompt="select_account",
        )

    def complete_login(
        self, flow: dict[str, Any], response: dict[str, str]
    ) -> dict[str, Any]:
        result = self._client()[0].acquire_token_by_auth_code_flow(flow, response)
        if "error" in result:
            description = result.get("error_description") or result["error"]
            raise RuntimeError(str(description))
        claims = result.get("id_token_claims")
        if not isinstance(claims, dict):
            raise RuntimeError("Microsoft no devolvió una identidad válida.")
        return claims

    def complete(self, flow: dict[str, Any], response: dict[str, str]) -> None:
        client, cache = self._client()
        result = client.acquire_token_by_auth_code_flow(flow, response)
        if "error" in result:
            description = result.get("error_description") or result["error"]
            raise RuntimeError(str(description))
        self._save_cache(cache)

    def access_token(self) -> str:
        client, cache = self._client()
        accounts = client.get_accounts(
            username=str(current_app.config.get("MICROSOFT_MAILBOX_ADDRESS") or "")
            or None
        )
        if not accounts:
            accounts = client.get_accounts()
        if not accounts:
            raise RuntimeError("Microsoft 365 requiere una nueva conexión.")
        result = client.acquire_token_silent(list(self.SCOPES), account=accounts[0])
        self._save_cache(cache)
        if not result or "access_token" not in result:
            raise RuntimeError("No fue posible renovar el acceso a Microsoft 365.")
        return str(result["access_token"])

    def _client(self) -> tuple[ConfidentialClientApplication, SerializableTokenCache]:
        cache = SerializableTokenCache()
        stored = IntegrationCredentialRepository.get(self.CREDENTIAL_KEY)
        if stored:
            cache.deserialize(stored)
        tenant = str(current_app.config.get("MICROSOFT_TENANT_ID") or "").strip()
        client = ConfidentialClientApplication(
            str(current_app.config.get("MICROSOFT_CLIENT_ID") or "").strip(),
            authority=f"https://login.microsoftonline.com/{tenant}",
            client_credential=str(
                current_app.config.get("MICROSOFT_CLIENT_SECRET") or ""
            ).strip(),
            token_cache=cache,
        )
        return client, cache

    def _save_cache(self, cache: SerializableTokenCache) -> None:
        if cache.has_state_changed:
            IntegrationCredentialRepository.save(
                self.CREDENTIAL_KEY, cache.serialize()
            )
