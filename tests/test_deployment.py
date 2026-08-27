from app import create_app


def test_healthcheck_is_public_and_checks_database(tmp_path, monkeypatch):
    monkeypatch.setattr("app.database.connection.DB_PATH", tmp_path / "health.db")
    application = create_app({"TESTING": True})

    response = application.test_client().get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
