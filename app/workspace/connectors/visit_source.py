from abc import ABC, abstractmethod
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
                 credentials_path: str):
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = worksheet_name
        self.credentials_path = credentials_path

    @classmethod
    def configuration_status(cls) -> dict:
        names = (
            "GOOGLE_VISITS_SPREADSHEET_ID",
            "GOOGLE_VISITS_WORKSHEET_NAME",
            "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH",
        )
        configured_values, sources = resolve_settings(names)
        values = {
            "spreadsheet_id": configured_values.get(names[0], ""),
            "worksheet_name": configured_values.get(names[1], ""),
            "credentials_path": configured_values.get(names[2], ""),
        }
        missing = [
            label for key, label in (
                ("spreadsheet_id", "GOOGLE_VISITS_SPREADSHEET_ID"),
                ("worksheet_name", "GOOGLE_VISITS_WORKSHEET_NAME"),
                (
                    "credentials_path",
                    "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH",
                ),
            )
            if not values[key]
        ]
        resolved_credentials = (
            resolve_file_path(
                values["credentials_path"], sources.get(names[2])
            )
            if values["credentials_path"] else None
        )
        credentials_available = bool(
            resolved_credentials and resolved_credentials.is_file()
        )
        configured = not missing
        return {
            **values,
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
                "No se encontró el archivo de credenciales de Google."
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
        return cls(
            spreadsheet_id=status["spreadsheet_id"],
            worksheet_name=status["worksheet_name"],
            credentials_path=status["credentials_path"],
        )

    def read_rows(self) -> list[dict]:
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Instale google-api-python-client y google-auth para sincronizar Google Sheets."
            ) from exc
        credentials = service_account.Credentials.from_service_account_file(
            self.credentials_path, scopes=self.SCOPES)
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
