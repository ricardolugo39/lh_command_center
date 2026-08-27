import sqlite3

from app.database.migrations import upgrade
from app.workspace.services.account_visit_analysis_service import AccountVisitAnalysisService


def test_visit_analysis_is_versioned_and_reused(tmp_path, monkeypatch):
    path = tmp_path / "analysis.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    monkeypatch.setattr(
        "app.workspace.services.account_visit_analysis_service.resolve_settings",
        lambda names: ({}, {}),
    )
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO ws_customers(id,name) VALUES (1,'Cliente')")
        connection.execute(
            """INSERT INTO ws_commercial_visits(
            source_system,source_visit_id,source_row_hash,visit_date,customer_id,
            customer_match_status,visit_type,requires_action,visit_status,
            detected_need,detected_risk,is_active,source_payload_json
            ) VALUES ('appsheet_google_sheets','V-1','hash-1','2026-08-01',1,
            'matched','Comercial',1,'Abierto','Repuestos','Competidor',1,'{}')"""
        )

    first = AccountVisitAnalysisService.generate(1, actor="tester")
    second = AccountVisitAnalysisService.generate(1, actor="tester")

    assert first["analysis"]["status"] == "deterministic"
    assert second["is_stale"] is False
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM account_visit_analyses"
        ).fetchone()[0] == 1
