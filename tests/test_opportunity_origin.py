import json
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.database.migrations import MIGRATION_MANIFEST, upgrade
from app.workspace.constants.opportunity_origin import OpportunityOrigin
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.services.project_workspace_service import (
    ProjectWorkspaceService,
)


@pytest.fixture
def origin_database(tmp_path, monkeypatch):
    path = tmp_path / "origin.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO ws_customers(id,name,erp_customer_id) "
            "VALUES (1,'Cliente','9001')"
        )
    return path


def _row(path, sql, params=()):
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        value = connection.execute(sql, params).fetchone()
        return dict(value) if value else None


def test_existing_records_backfill_and_preserve_children(tmp_path, monkeypatch):
    path = tmp_path / "legacy-origin.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        origin_migration_index = next(
            index
            for index, migration in enumerate(MIGRATION_MANIFEST)
            if migration.version == 27
        )
        for migration in MIGRATION_MANIFEST[:origin_migration_index]:
            migration.apply(connection)
        connection.execute(
            "CREATE TABLE schema_migrations("
            "version INTEGER PRIMARY KEY,name TEXT UNIQUE,applied_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO schema_migrations VALUES (?,?,CURRENT_TIMESTAMP)",
                [
                    (item.version, item.name)
                    for item in MIGRATION_MANIFEST[:origin_migration_index]
                ],
        )
        connection.execute(
            "INSERT INTO ws_customers(id,name,erp_customer_id) "
            "VALUES (1,'Cliente','9001')"
        )
        connection.execute(
            "INSERT INTO ws_projects(id,customer_id,name,status,objective) "
            "VALUES (7,1,'Manual','prospect','Objetivo')"
        )
        connection.execute(
            "INSERT INTO ws_projects(id,customer_id,name,status,objective) "
            "VALUES (8,1,'Desde visita','prospect','Objetivo')"
        )
        connection.execute(
            "INSERT INTO ws_activities(project_id,activity_type,title) "
            "VALUES (7,'note','Actividad')"
        )
        connection.execute(
            "INSERT INTO ws_followups(project_id,due_date,description,status) "
            "VALUES (7,'2026-08-01','Seguimiento','pending')"
        )
        connection.execute(
            "INSERT INTO ws_commercial_visits("
            "source_system,source_visit_id,source_row_hash,visit_type,"
            "visit_status,source_payload_json,project_id"
            ") VALUES ('appsheet_google_sheets','VIS-44','hash','Visita',"
            "'Abierta','{}',8)"
        )

    report = upgrade()

    assert 27 in report.applied_versions
    manual = _row(path, "SELECT * FROM ws_projects WHERE id=7")
    visit = _row(path, "SELECT * FROM ws_projects WHERE id=8")
    assert manual["origin"] == "manual"
    assert manual["external_id"] is None
    assert visit["origin"] == "visit"
    assert visit["origin_reference"] == "VIS-44"
    assert _row(
        path, "SELECT project_id FROM ws_activities WHERE project_id=7"
    )["project_id"] == 7
    assert _row(
        path, "SELECT project_id FROM ws_followups WHERE project_id=7"
    )["project_id"] == 7


def test_manual_origin_default_and_null_external_ids_are_repeatable(
    origin_database,
):
    first = ProjectRepository.create_project(1, "A", "Objetivo")
    second = ProjectRepository.create_project(1, "B", "Objetivo")

    assert ProjectRepository.get_project(first)["origin"] == "manual"
    assert ProjectRepository.get_project(second)["origin"] == "manual"


def test_crm_identity_is_unique_and_lookup_is_stable(origin_database):
    timestamp = datetime.now(timezone.utc).isoformat()
    first = ProjectRepository.create_project(
        1,
        "CRM",
        "Objetivo",
        origin="crm",
        external_id="CRM-100",
        origin_reference="OP-100",
        imported_at=timestamp,
    )

    with pytest.raises(sqlite3.IntegrityError):
        ProjectRepository.create_project(
            1,
            "Duplicada",
            "Objetivo",
            origin="crm",
            external_id="CRM-100",
            imported_at=timestamp,
        )

    found = ProjectRepository.find_by_origin_external_id("crm", "CRM-100")
    assert found["id"] == first
    assert found["origin_reference"] == "OP-100"


def test_crm_origin_requires_external_id(origin_database):
    with pytest.raises(ValueError, match="external ID"):
        ProjectRepository.create_project(
            1, "CRM", "Objetivo", origin=OpportunityOrigin.CRM
        )


def test_origin_and_creation_identity_are_immutable(origin_database):
    project_id = ProjectRepository.create_project(
        1,
        "CRM",
        "Objetivo",
        origin="crm",
        external_id="CRM-immutable",
        origin_reference="REF-1",
        imported_at="2026-07-30T10:00:00+00:00",
    )

    for assignment in (
        "origin='manual'",
        "external_id='CRM-other'",
        "origin_reference='REF-2'",
        "imported_at='2026-07-31T10:00:00+00:00'",
    ):
        with sqlite3.connect(origin_database) as connection:
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(
                    f"UPDATE ws_projects SET {assignment} WHERE id=?",
                    (project_id,),
                )


def test_synchronization_audit_updates_only_mutable_audit_fields(
    origin_database,
):
    with sqlite3.connect(origin_database) as connection:
        connection.execute(
            """
            INSERT INTO erp_import_executions(
                import_type,original_filename,stored_file_path,file_hash,
                schema_version,status,executed_by
            ) VALUES ('sales','crm.xlsx','file','hash','v1',
                      'completed','admin')
            """
        )
        execution_id = connection.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]
    project_id = ProjectRepository.create_project(
        1,
        "CRM",
        "Objetivo",
        origin="crm",
        external_id="CRM-audit",
        origin_reference="AUD-1",
        imported_at="2026-07-30T10:00:00+00:00",
        created_import_execution_id=execution_id,
        last_import_execution_id=execution_id,
        import_metadata=json.dumps({"profile_version": 1}),
    )

    ProjectRepository.update_synchronization_audit(
        project_id,
        last_synchronized_at="2026-07-31T10:00:00+00:00",
        last_import_execution_id=execution_id,
        import_metadata=json.dumps({"profile_version": 1, "rows": [2]}),
    )

    project = ProjectRepository.get_project(project_id)
    assert project["origin"] == "crm"
    assert project["created_import_execution_id"] == execution_id
    assert project["last_import_execution_id"] == execution_id
    assert project["last_synchronized_at"].startswith("2026-07-31")


def test_visit_creation_assigns_visit_origin(origin_database):
    with (
        patch(
            "app.workspace.services.project_workspace_service."
            "CustomerLookupRepository.get_customer_site",
            return_value={
                "customer_id": "9001",
                "customer_name": "Cliente",
            },
        ),
        patch(
            "app.workspace.services.project_workspace_service."
            "CustomerRepository.find_by_erp_customer_id",
            return_value={"id": 1},
        ),
        patch(
            "app.workspace.services.project_workspace_service."
            "ActivityRepository.create_activity",
        ),
        patch(
            "app.workspace.services.commercial_visit_service."
            "CommercialVisitService.link_to_project",
        ),
        patch.object(
            ProjectWorkspaceService,
            "get_workspace",
            side_effect=lambda project_id: {
                "project": ProjectRepository.get_project(project_id)
            },
        ),
    ):
        workspace = ProjectWorkspaceService.create_project_mvp(
            erp_customer_id="9001",
            customer_site_id="SITE-1",
            project_name="Desde visita",
            objective="Objetivo",
            sales_rep="Ana",
            source_visit_id=44,
        )

    assert workspace["project"]["origin"] == "visit"
    assert workspace["project"]["origin_reference"] == "44"
