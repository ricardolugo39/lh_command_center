from bs4 import BeautifulSoup
import pytest

from app import create_app


@pytest.fixture
def integration_client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.database.connection.DB_PATH", tmp_path / "integrations.db"
    )
    for name in (
        "GOOGLE_VISITS_SPREADSHEET_ID",
        "GOOGLE_VISITS_WORKSHEET_NAME",
        "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "app.configuration.LEGACY_ENV_PATH",
        tmp_path / "no-legacy-configuration.env",
    )
    monkeypatch.setattr(
        "app.configuration.LEGACY_CREDENTIALS_DIR",
        tmp_path / "no-legacy-credentials",
    )
    return create_app({
        "TESTING": True, "TEST_AUTH_BYPASS": True,
    }).test_client()


def test_unified_integration_center_shows_erp_and_google(
    integration_client,
):
    response = integration_client.get("/integrations/")

    assert response.status_code == 200
    assert b"Clientes y ventas" in response.data
    assert b"Google AppSheet / Google Sheets" in response.data
    assert b"Pendiente de configuraci\xc3\xb3n" in response.data
    assert b"La integraci\xc3\xb3n est\xc3\xa1 disponible" in response.data


def test_navigation_has_one_integrations_entry(integration_client):
    response = integration_client.get("/integrations/")
    document = BeautifulSoup(response.data, "html.parser")
    navigation = document.select_one("aside")
    links = navigation.select('a[href="/integrations/"]')

    assert len(links) == 1
    assert links[0]["href"] == "/integrations/"
    assert "Importaciones ERP" not in navigation.get_text(" ", strip=True)


def test_legacy_erp_and_visit_routes_remain_available(integration_client):
    assert integration_client.get("/imports/").status_code == 200
    visit = integration_client.get(
        "/workspace/integrations/google/visits"
    )
    quality = integration_client.get(
        "/workspace/integrations/google/visits/quality"
    )

    assert visit.status_code == 200
    assert quality.status_code == 200
    assert b"Integraci\xc3\xb3n habilitada" in visit.data
    document = BeautifulSoup(visit.data, "html.parser")
    button = document.select_one(
        'form[action="/workspace/integrations/google/visits/sync"] button'
    )
    assert button is not None
    assert not button.has_attr("disabled")


def test_configured_google_integration_keeps_manual_sync_action(
    integration_client, tmp_path, monkeypatch,
):
    credentials = tmp_path / "google-service-account.json"
    credentials.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_VISITS_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setenv("GOOGLE_VISITS_WORKSHEET_NAME", "Visitas")
    monkeypatch.setenv(
        "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH", str(credentials)
    )

    response = integration_client.get(
        "/workspace/integrations/google/visits"
    )

    assert response.status_code == 200
    assert b"Configurada" in response.data
    assert b"Sincronizar ahora" in response.data
    document = BeautifulSoup(response.data, "html.parser")
    button = document.select_one(
        'form[action="/workspace/integrations/google/visits/sync"] button'
    )
    assert button is not None
    assert not button.has_attr("disabled")


def test_missing_credential_file_is_reported_without_breaking_page(
    integration_client, tmp_path, monkeypatch,
):
    monkeypatch.setenv("GOOGLE_VISITS_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setenv("GOOGLE_VISITS_WORKSHEET_NAME", "Visitas")
    monkeypatch.setenv(
        "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH",
        str(tmp_path / "missing.json"),
    )

    response = integration_client.get("/integrations/")

    assert response.status_code == 200
    assert b"Requiere credenciales" in response.data
    assert b"No se encontr\xc3\xb3 el archivo" in response.data


def test_legacy_external_env_and_relative_credential_path_are_supported(
    tmp_path, monkeypatch,
):
    credentials_dir = tmp_path / "legacy-credentials"
    credentials_dir.mkdir()
    credentials = credentials_dir / "service-account.json"
    credentials.write_text("{}", encoding="utf-8")
    legacy_env = credentials_dir / ".env"
    legacy_env.write_text(
        "\n".join((
            "GOOGLE_VISITS_SPREADSHEET_ID=legacy-sheet",
            "GOOGLE_VISITS_WORKSHEET_NAME=Visitas",
            "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH=service-account.json",
        )),
        encoding="utf-8",
    )
    for name in (
        "GOOGLE_VISITS_SPREADSHEET_ID",
        "GOOGLE_VISITS_WORKSHEET_NAME",
        "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.configuration.LEGACY_ENV_PATH", legacy_env)
    monkeypatch.setattr(
        "app.configuration.LEGACY_CREDENTIALS_DIR", credentials_dir
    )

    from app.workspace.connectors.visit_source import GoogleSheetsVisitSource

    status = GoogleSheetsVisitSource.configuration_status()
    source = GoogleSheetsVisitSource.from_environment()

    assert status["configured"] is True
    assert status["ready"] is True
    assert status["credentials_path"] == str(credentials.resolve())
    assert source.spreadsheet_id == "legacy-sheet"
    assert source.credentials_path == str(credentials.resolve())


def test_project_config_py_remains_a_supported_configuration_source(
    tmp_path, monkeypatch,
):
    credentials = tmp_path / "credentials.json"
    credentials.write_text("{}", encoding="utf-8")
    config = tmp_path / "config.py"
    config.write_text(
        "\n".join((
            "class Config:",
            "    GOOGLE_VISITS_SPREADSHEET_ID = 'config-sheet'",
            "    GOOGLE_VISITS_WORKSHEET_NAME = 'Visitas Config'",
            f"    GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH = {str(credentials)!r}",
        )),
        encoding="utf-8",
    )
    for name in (
        "GOOGLE_VISITS_SPREADSHEET_ID",
        "GOOGLE_VISITS_WORKSHEET_NAME",
        "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.configuration.PROJECT_CONFIG_PATH", config)
    monkeypatch.setattr(
        "app.configuration.PROJECT_ENV_PATH", tmp_path / "missing.env"
    )
    monkeypatch.setattr(
        "app.configuration.LEGACY_ENV_PATH", tmp_path / "legacy-missing.env"
    )

    from app.workspace.connectors.visit_source import GoogleSheetsVisitSource

    status = GoogleSheetsVisitSource.configuration_status()

    assert status["ready"] is True
    assert status["spreadsheet_id"] == "config-sheet"
    assert status["worksheet_name"] == "Visitas Config"
