from abc import ABC, abstractmethod
import json
from pathlib import Path

from app.configuration import resolve_file_path, resolve_settings


class VisitSourceAdapter(ABC):
    @abstractmethod
    def read_rows(self) -> list[dict]:
        """Return source rows without applying business rules."""


class GoogleSheetsVisitSource(VisitSourceAdapter):
    """Read one configured worksheet through a read-only service account."""

    SCOPES = ("https://www.googleapis.com/auth/spreadsheets.readonly",)

    def __init__(self, spreadsheet_id: str, worksheet_name: str,
                 credentials_path: str = "", credentials_info: dict | None = None):
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = worksheet_name
        self.credentials_path = credentials_path
        self.credentials_info = credentials_info

    @classmethod
    def configuration_status(cls) -> dict:
        names = (
            "GOOGLE_VISITS_SPREADSHEET_ID",
            "GOOGLE_VISITS_WORKSHEET_NAME",
            "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH",
            "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_JSON",
        )
        configured_values, sources = resolve_settings(names)
        values = {
            "spreadsheet_id": configured_values.get(names[0], ""),
            "worksheet_name": configured_values.get(names[1], ""),
            "credentials_path": configured_values.get(names[2], ""),
            "credentials_json": configured_values.get(names[3], ""),
        }
        missing = [
            label for key, label in (
                ("spreadsheet_id", "GOOGLE_VISITS_SPREADSHEET_ID"),
                ("worksheet_name", "GOOGLE_VISITS_WORKSHEET_NAME"),
            )
            if not values[key]
        ]
        if not values["credentials_path"] and not values["credentials_json"]:
            missing.append(
                "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_JSON o "
                "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH"
            )
        resolved_credentials = (
            resolve_file_path(
                values["credentials_path"], sources.get(names[2])
            )
            if values["credentials_path"] else None
        )
        credentials_info = None
        credentials_json_valid = False
        if values["credentials_json"]:
            try:
                credentials_info = json.loads(values["credentials_json"])
                credentials_json_valid = bool(
                    isinstance(credentials_info, dict)
                    and credentials_info.get("client_email")
                    and credentials_info.get("private_key")
                )
            except (TypeError, ValueError):
                pass
        credentials_available = credentials_json_valid or bool(
            resolved_credentials and resolved_credentials.is_file()
        )
        configured = not missing
        return {
            "spreadsheet_id": values["spreadsheet_id"],
            "worksheet_name": values["worksheet_name"],
            "credentials_path": (
                str(resolved_credentials) if resolved_credentials else ""
            ),
            "available": True,
            "configured": configured,
            "ready": configured and credentials_available,
            "credentials_available": credentials_available,
            "missing_settings": missing,
            "configuration_sources": {
                name: str(source) if source else "environment"
                for name, source in sources.items()
            },
            "configuration_error": (
                (
                    "No se encontró el archivo de credenciales de Google."
                    if values["credentials_path"]
                    else "Las credenciales JSON de Google no son válidas."
                )
                if configured and not credentials_available else None
            ),
        }

    @classmethod
    def from_environment(cls):
        status = cls.configuration_status()
        if not status["configured"]:
            raise ValueError("La integración de Google Sheets no está configurada.")
        if not status["credentials_available"]:
            raise ValueError("No se encontró el archivo de credenciales de Google.")
        configured_values, _ = resolve_settings(
            ("GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_JSON",)
        )
        raw_credentials = configured_values.get(
            "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_JSON", ""
        )
        credentials_info = json.loads(raw_credentials) if raw_credentials else None
        return cls(
            spreadsheet_id=status["spreadsheet_id"],
            worksheet_name=status["worksheet_name"],
            credentials_path=status["credentials_path"],
            credentials_info=credentials_info,
        )

    def read_rows(self) -> list[dict]:
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Instale google-api-python-client y google-auth para sincronizar Google Sheets."
            ) from exc
        credentials = (
            service_account.Credentials.from_service_account_info(
                self.credentials_info, scopes=self.SCOPES
            )
            if self.credentials_info
            else service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=self.SCOPES
            )
        )
        service = build("sheets", "v4", credentials=credentials,
                        cache_discovery=False)
        values = service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.worksheet_name}'").execute().get("values", [])
        if not values:
            return []
        headers = [str(value).strip() for value in values[0]]
        return [
            {header: row[index] if index < len(row) else ""
             for index, header in enumerate(headers)}
            for row in values[1:]
            if any(str(value).strip() for value in row)
        ]
