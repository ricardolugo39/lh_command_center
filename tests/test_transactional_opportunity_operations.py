import sqlite3
import threading
from io import BytesIO
from unittest.mock import patch

import pytest
from werkzeug.datastructures import FileStorage

from app.database.connection import get_connection
from app.database.transaction import transaction, transactional
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.services.project_closure_service import ProjectClosureService
from app.workspace.services.project_file_service import ProjectFileService
from app.workspace.services.project_workspace_service import ProjectWorkspaceService


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE ws_customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    erp_customer_id TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE ws_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    customer_site_id TEXT,
    initiative_id INTEGER,
    sales_rep TEXT,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    objective TEXT NOT NULL,
    proposed_solution TEXT,
    current_blocker TEXT,
    commercial_amount NUMERIC,
    commercial_currency TEXT,
    origin TEXT NOT NULL DEFAULT 'manual',
    external_id TEXT,
    origin_reference TEXT,
    imported_at TEXT,
    last_synchronized_at TEXT,
    created_import_execution_id INTEGER,
    last_import_execution_id INTEGER,
    import_metadata TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT,
    close_reason TEXT,
    close_comments TEXT,
    competitor_company TEXT,
    competitor_type TEXT,
    competitor_brand TEXT,
    won_amount REAL,
    order_number TEXT,
    customer_po TEXT,
    result_changer TEXT
);
CREATE TABLE ws_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    activity_type TEXT NOT NULL,
    title TEXT NOT NULL,
    details TEXT,
    created_by TEXT,
    occurred_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE ws_project_brands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    brand TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, brand)
);
CREATE TABLE ws_project_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    quote_number TEXT NOT NULL,
    branch TEXT,
    prefix TEXT NOT NULL,
    quote_date TEXT,
    amount REAL,
    quote_status TEXT,
    erp_user TEXT,
    currency_code TEXT DEFAULT 'COP',
    exchange_rate REAL,
    normalized_amount REAL,
    revision INTEGER DEFAULT 0,
    exchange_rate_type TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture
def opportunity_db(tmp_path, monkeypatch):
    database_path = tmp_path / "opportunities.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA)

    monkeypatch.setattr(
        "app.database.connection.DB_PATH",
        database_path,
    )
    return database_path


def _insert_open_project(database_path) -> int:
    with sqlite3.connect(database_path) as connection:
        customer_id = connection.execute(
            "INSERT INTO ws_customers (name) VALUES ('Cliente')"
        ).lastrowid
        project_id = connection.execute(
            """
            INSERT INTO ws_projects (
                customer_id, sales_rep, name, status, objective
            ) VALUES (?, 'Ana', 'Oportunidad', 'negotiation', 'Objetivo')
            """,
            (customer_id,),
        ).lastrowid
    return int(project_id)


def test_nested_service_transactions_share_outer_rollback(opportunity_db):
    @transactional
    def inner():
        with transaction() as connection:
            connection.execute(
                "INSERT INTO ws_customers (name) VALUES ('Anidado')"
            )

    @transactional
    def outer():
        inner()
        raise RuntimeError("fallo posterior")

    with pytest.raises(RuntimeError):
        outer()

    with sqlite3.connect(opportunity_db) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM ws_customers"
        ).fetchone()[0]
    assert count == 0


def test_sqlite_connection_allows_write_commit_during_active_read(
    opportunity_db,
):
    project_id = _insert_open_project(opportunity_db)
    reader = get_connection()
    try:
        assert reader.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert reader.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        reader.execute("BEGIN")
        reader.execute(
            "SELECT name FROM ws_projects WHERE id=?", (project_id,)
        ).fetchone()

        with transaction(write=True) as writer:
            writer.execute(
                "UPDATE ws_projects SET name='Actualizada' WHERE id=?",
                (project_id,),
            )

        assert reader.execute(
            "SELECT name FROM ws_projects WHERE id=?", (project_id,)
        ).fetchone()[0] == "Oportunidad"
    finally:
        reader.rollback()
        reader.close()

    with sqlite3.connect(opportunity_db) as connection:
        assert connection.execute(
            "SELECT name FROM ws_projects WHERE id=?", (project_id,)
        ).fetchone()[0] == "Actualizada"


def test_opportunity_creation_rolls_back_when_activity_fails(opportunity_db):
    with patch(
        "app.workspace.services.project_workspace_service."
        "ActivityRepository.create_activity",
        side_effect=RuntimeError("audit failure"),
    ):
        with pytest.raises(RuntimeError):
            ProjectWorkspaceService.start_project(
                customer_name="Cliente",
                project_name="Oportunidad",
                objective="Objetivo",
            )

    with sqlite3.connect(opportunity_db) as connection:
        customer_count = connection.execute(
            "SELECT COUNT(*) FROM ws_customers"
        ).fetchone()[0]
        project_count = connection.execute(
            "SELECT COUNT(*) FROM ws_projects"
        ).fetchone()[0]

    assert (customer_count, project_count) == (0, 0)


def test_closure_rolls_back_when_audit_fails(opportunity_db):
    project_id = _insert_open_project(opportunity_db)

    with patch(
        "app.workspace.services.project_closure_service."
        "ActivityRepository.create_activity",
        side_effect=RuntimeError("audit failure"),
    ):
        with pytest.raises(RuntimeError):
            ProjectClosureService.cancel(
                project_id=project_id,
                reason="Sin presupuesto",
            )

    with sqlite3.connect(opportunity_db) as connection:
        status, closed_at = connection.execute(
            "SELECT status, closed_at FROM ws_projects WHERE id = ?",
            (project_id,),
        ).fetchone()

    assert status == "negotiation"
    assert closed_at is None


def test_quote_replacement_rolls_back_with_project_update(opportunity_db):
    project_id = _insert_open_project(opportunity_db)
    with sqlite3.connect(opportunity_db) as connection:
        connection.execute(
            """
            INSERT INTO ws_project_quotes (
                project_id, prefix, quote_number, amount
            ) VALUES (?, 'CTC', 'ORIGINAL', 10)
            """,
            (project_id,),
        )

    with patch(
        "app.workspace.services.project_workspace_service."
        "ActivityRepository.create_activity",
        side_effect=RuntimeError("audit failure"),
    ):
        with pytest.raises(RuntimeError):
            ProjectWorkspaceService.update_project_details(
                project_id=project_id,
                project_name="Nombre cambiado",
                objective="Objetivo cambiado",
                proposed_solution=None,
                current_blocker=None,
                sales_rep="Ana",
                quote_number="NUEVA",
                quote_amount=20,
            )

    with sqlite3.connect(opportunity_db) as connection:
        project_name = connection.execute(
            "SELECT name FROM ws_projects WHERE id = ?",
            (project_id,),
        ).fetchone()[0]
        quotes = connection.execute(
            "SELECT quote_number FROM ws_project_quotes WHERE project_id = ?",
            (project_id,),
        ).fetchall()

    assert project_name == "Oportunidad"
    assert quotes == [("ORIGINAL",)]


def test_concurrent_update_waits_for_closure_and_is_rejected(opportunity_db):
    project_id = _insert_open_project(opportunity_db)
    closure_updated = threading.Event()
    allow_closure_commit = threading.Event()
    errors = []

    original_cancel = ProjectRepository.cancel_project

    def pausing_cancel(**kwargs):
        original_cancel(**kwargs)
        closure_updated.set()
        assert allow_closure_commit.wait(timeout=3)

    def close_project():
        try:
            with (
                patch.object(
                    ProjectRepository,
                    "cancel_project",
                    side_effect=pausing_cancel,
                ),
                patch.object(
                    ProjectWorkspaceService,
                    "get_workspace",
                    return_value={},
                ),
            ):
                ProjectClosureService.cancel(
                    project_id=project_id,
                    reason="Cancelada",
                )
        except Exception as exc:  # Captured for assertion in the main thread.
            errors.append(exc)

    update_error = []

    def update_project():
        try:
            ProjectWorkspaceService.change_blocker(
                project_id=project_id,
                new_blocker="No debe guardarse",
            )
        except Exception as exc:
            update_error.append(exc)

    closure_thread = threading.Thread(target=close_project)
    closure_thread.start()
    assert closure_updated.wait(timeout=3)

    update_thread = threading.Thread(target=update_project)
    update_thread.start()
    allow_closure_commit.set()

    closure_thread.join(timeout=5)
    update_thread.join(timeout=5)

    assert not errors
    assert len(update_error) == 1
    assert "solo lectura" in str(update_error[0])

    with sqlite3.connect(opportunity_db) as connection:
        status, blocker = connection.execute(
            "SELECT status, current_blocker FROM ws_projects WHERE id = ?",
            (project_id,),
        ).fetchone()

    assert status == "cancelled"
    assert blocker is None


def test_failed_file_upload_removes_saved_file(
    opportunity_db, tmp_path, monkeypatch
):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(
        "app.workspace.services.project_file_service.UPLOAD_ROOT",
        upload_root,
    )
    uploaded_file = FileStorage(
        stream=BytesIO(b"contenido"),
        filename="cotizacion.pdf",
        content_type="application/pdf",
    )

    with (
        patch(
            "app.workspace.services.project_file_service."
            "ProjectAccessPolicy.require_writable",
            return_value={"id": 1, "status": "prospect"},
        ),
        patch(
            "app.workspace.services.project_file_service."
            "ProjectFileRepository.create_file",
            side_effect=RuntimeError("database failure"),
        ),
    ):
        with pytest.raises(RuntimeError):
            ProjectFileService.upload_file(
                project_id=1,
                file=uploaded_file,
                category="quote",
            )

    assert not list(upload_root.rglob("*.pdf"))


def test_failed_file_delete_restores_staged_file(
    opportunity_db, tmp_path, monkeypatch
):
    upload_root = tmp_path / "uploads"
    project_folder = upload_root / "1"
    project_folder.mkdir(parents=True)
    original_path = project_folder / "archivo.pdf"
    original_path.write_bytes(b"contenido")

    monkeypatch.setattr(
        "app.workspace.services.project_file_service.UPLOAD_ROOT",
        upload_root,
    )
    record = {
        "id": 9,
        "project_id": 1,
        "stored_name": "archivo.pdf",
    }

    with (
        patch(
            "app.workspace.services.project_file_service."
            "ProjectFileRepository.get_file",
            return_value=record,
        ),
        patch(
            "app.workspace.services.project_file_service."
            "ProjectAccessPolicy.require_writable",
            return_value={"id": 1, "status": "prospect"},
        ),
        patch(
            "app.workspace.services.project_file_service."
            "ProjectFileRepository.delete_file",
            side_effect=RuntimeError("database failure"),
        ),
    ):
        with pytest.raises(RuntimeError):
            ProjectFileService.delete_file(9)

    assert original_path.read_bytes() == b"contenido"
    assert not list(project_folder.glob("*.deleting"))
