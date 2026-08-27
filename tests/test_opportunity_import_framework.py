import io
import json
import sqlite3

import pandas as pd
import pytest
from werkzeug.datastructures import FileStorage

from app.database.migrations import upgrade
from app.database.migrations import MIGRATION_MANIFEST
from app.workspace.repositories.opportunity_import_repository import (
    OpportunityImportRepository,
)
from app.workspace.services.opportunity_import_profile_service import (
    OpportunityImportProfileError,
    OpportunityImportProfileService,
)
from app.workspace.services.opportunity_import_service import (
    OpportunityImportService,
    OpportunityImportValidationError,
)


@pytest.fixture
def opportunity_import_database(tmp_path, monkeypatch):
    path = tmp_path / "opportunity-import.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    monkeypatch.setattr(
        OpportunityImportService, "STORAGE_ROOT", tmp_path / "imports"
    )
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.executemany(
            "INSERT INTO ws_customers(id,name,erp_customer_id) VALUES (?,?,?)",
            [(1, "Cliente Uno", "900.100-1"), (2, "Cliente Dos", "9002002")],
        )
    OpportunityImportProfileService.create_profile(
        "CRM genérico",
        mapping={
            "external_opportunity_id": "CRM ID",
            "origin_reference": "Referencia",
            "customer_identity": "NIT",
            "opportunity_name": "Nombre",
            "objective": "Objetivo",
            "seller": "Vendedor",
            "stage": "Etapa",
            "potential_value": "Valor potencial",
        },
        transformations={
            "external_opportunity_id": "trim_text",
            "customer_identity": "trim_text",
            "opportunity_name": "trim_text",
            "potential_value": "parse_decimal",
            "stage": {
                "name": "controlled_value",
                "options": {
                    "mapping": {
                        "Abierta": "prospect", "Cotizada": "quoted",
                        "Ganada": "won",
                    }
                },
            },
        },
        grouping={
            "consistent_concepts": [
                "customer_identity", "opportunity_name"
            ]
        },
        ownership={
            "import_owned_fields": ["name", "objective", "sales_rep", "status"]
        },
        created_by="tester",
        activate=True,
    )
    return path


def _upload(rows, filename="crm.xlsx"):
    stream = io.BytesIO()
    dataframe = pd.DataFrame(rows)
    if filename.endswith(".csv"):
        stream.write(dataframe.to_csv(index=False).encode())
    else:
        dataframe.to_excel(stream, index=False)
    stream.seek(0)
    return FileStorage(stream=stream, filename=filename)


def _row(external_id="CRM-1", nit="9001001", name="Oportunidad A"):
    return {
        "CRM ID": external_id, "Referencia": f"REF-{external_id}",
        "NIT": nit, "Nombre": name, "Objetivo": "Vender",
        "Vendedor": "Ana", "Etapa": "Abierta", "Valor potencial": "9000000",
    }


def test_profile_registry_rejects_unknown_concepts_and_executable_rules(
    opportunity_import_database,
):
    with pytest.raises(OpportunityImportProfileError, match="desconocidos"):
        OpportunityImportProfileService.validate({
            "external_opportunity_id": "ID", "customer_identity": "NIT",
            "opportunity_name": "Nombre", "invented": "X",
        })
    with pytest.raises(OpportunityImportProfileError, match="no permitida"):
        OpportunityImportProfileService.validate(
            {
                "external_opportunity_id": "ID",
                "customer_identity": "NIT",
                "opportunity_name": "Nombre",
            },
            {"opportunity_name": "eval_python"},
        )


def test_profile_versions_are_immutable(opportunity_import_database):
    profile = OpportunityImportRepository.active_version()
    with sqlite3.connect(opportunity_import_database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE opportunity_import_profile_versions "
                "SET column_mapping_json='{}' WHERE id=?",
                (profile["id"],),
            )


def test_preview_groups_rows_and_allows_partial_confirmation(
    opportunity_import_database,
):
    rows = [_row(), _row(), _row("CRM-2", "unknown", "Oportunidad B")]
    preview = OpportunityImportService.prepare(
        upload=_upload(rows), executed_by="tester"
    )

    assert preview.rows_read == 3
    assert preview.metrics == {
        "groups_identified": 2, "groups_to_create": 1,
        "groups_to_update": 0, "groups_unchanged": 0,
        "groups_needs_review": 1, "groups_blocked": 0,
        "groups_eligible": 1, "groups_deferred": 1,
    }
    assert preview.groups[0]["source_rows"] == 2
    assert preview.can_confirm
    with sqlite3.connect(opportunity_import_database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ws_projects").fetchone()[0] == 0

    resolved = OpportunityImportService.resolve_customer(
        preview.execution_id, "CRM-2", customer_id=2, resolved_by="reviewer"
    )
    assert resolved.can_confirm
    OpportunityImportService.confirm(
        preview.execution_id, confirmed=True, executed_by="tester"
    )
    with sqlite3.connect(opportunity_import_database) as connection:
        projects = connection.execute(
            "SELECT origin,external_id,origin_reference FROM ws_projects ORDER BY external_id"
        ).fetchall()
    assert projects == [
        ("crm", "CRM-1", "REF-CRM-1"),
        ("crm", "CRM-2", "REF-CRM-2"),
    ]


def test_inconsistent_group_is_blocked_and_never_creates_orphan(
    opportunity_import_database,
):
    first = _row()
    second = _row()
    second["NIT"] = "9002002"
    preview = OpportunityImportService.prepare(
        upload=_upload([first, second]), executed_by="tester"
    )
    assert preview.groups[0]["action"] == "blocked"
    result = OpportunityImportService.confirm(
        preview.execution_id, confirmed=True, executed_by="tester"
    )
    assert result["status"] == "completed"
    assert result["groups_deferred"] == 1
    with sqlite3.connect(opportunity_import_database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ws_projects").fetchone()[0] == 0


def test_reimport_updates_in_place_and_preserves_value_and_children(
    opportunity_import_database,
):
    first = OpportunityImportService.prepare(
        upload=_upload([_row()]), executed_by="tester"
    )
    OpportunityImportService.confirm(
        first.execution_id, confirmed=True, executed_by="tester"
    )
    with sqlite3.connect(opportunity_import_database) as connection:
        project_id = connection.execute(
            "SELECT id FROM ws_projects WHERE external_id='CRM-1'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE ws_projects SET commercial_amount=123456, "
            "commercial_currency='COP' WHERE id=?", (project_id,)
        )
        connection.execute(
            "INSERT INTO ws_activities(project_id,activity_type,title) "
            "VALUES (?,'note','Evidencia')", (project_id,)
        )

    changed = _row(name="Nombre actualizado")
    changed["Valor potencial"] = "99999999"
    second = OpportunityImportService.prepare(
        upload=_upload([changed]), executed_by="tester"
    )
    assert second.groups[0]["action"] == "update"
    result = OpportunityImportService.confirm(
        second.execution_id, confirmed=True, executed_by="tester"
    )
    assert result["rows_updated"] == 1
    with sqlite3.connect(opportunity_import_database) as connection:
        connection.row_factory = sqlite3.Row
        project = dict(connection.execute(
            "SELECT * FROM ws_projects WHERE external_id='CRM-1'"
        ).fetchone())
        activities = connection.execute(
            "SELECT COUNT(*) FROM ws_activities WHERE project_id=?",
            (project_id,),
        ).fetchone()[0]
    assert project["id"] == project_id
    assert project["name"] == "Nombre actualizado"
    assert float(project["commercial_amount"]) == 123456
    assert activities == 1
    assert json.loads(project["import_metadata"])["source_facts"]["potential_value"] == 99999999


def test_unknown_headers_fail_before_any_opportunity_write(
    opportunity_import_database,
):
    row = _row()
    del row["CRM ID"]
    with pytest.raises(OpportunityImportValidationError, match="columnas"):
        OpportunityImportService.prepare(
            upload=_upload([row]), executed_by="tester"
        )
    with sqlite3.connect(opportunity_import_database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ws_projects").fetchone()[0] == 0


def test_framework_migration_preserves_existing_import_links(tmp_path, monkeypatch):
    path = tmp_path / "before-framework.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        for migration in MIGRATION_MANIFEST[:27]:
            migration.apply(connection)
        connection.execute(
            "CREATE TABLE schema_migrations("
            "version INTEGER PRIMARY KEY,name TEXT UNIQUE,applied_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO schema_migrations VALUES (?,?,CURRENT_TIMESTAMP)",
            [(item.version, item.name) for item in MIGRATION_MANIFEST[:27]],
        )
        connection.execute(
            "INSERT INTO ws_customers(id,name,erp_customer_id) "
            "VALUES (1,'Cliente','9001')"
        )
        execution_id = connection.execute(
            """INSERT INTO erp_import_executions(
                import_type,original_filename,stored_file_path,file_hash,
                schema_version,status,executed_by
            ) VALUES ('customers','a.csv','a.csv','hash','v1','completed','test')"""
        ).lastrowid
        connection.execute(
            """INSERT INTO ws_projects(
                customer_id,name,status,objective,origin,external_id,
                imported_at,created_import_execution_id,last_import_execution_id
            ) VALUES (1,'CRM','prospect','Objetivo','crm','X','now',?,?)""",
            (execution_id, execution_id),
        )

    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        project = connection.execute(
            "SELECT created_import_execution_id FROM ws_projects"
        ).fetchone()
        assert project == (execution_id,)


def test_closed_lifecycle_conflict_is_blocked(opportunity_import_database):
    initial = _row()
    initial["Etapa"] = "Ganada"
    preview = OpportunityImportService.prepare(
        upload=_upload([initial]), executed_by="tester"
    )
    OpportunityImportService.confirm(
        preview.execution_id, confirmed=True, executed_by="tester"
    )
    reopened = _row()
    conflict = OpportunityImportService.prepare(
        upload=_upload([reopened]), executed_by="tester"
    )
    assert conflict.groups[0]["action"] == "blocked"
    assert "ciclo de vida" in conflict.groups[0]["blocked_reason"]


def test_confirmation_revalidates_retained_file(opportunity_import_database):
    preview = OpportunityImportService.prepare(
        upload=_upload([_row()]), executed_by="tester"
    )
    with sqlite3.connect(opportunity_import_database) as connection:
        stored_path = connection.execute(
            "SELECT stored_file_path FROM erp_import_executions WHERE id=?",
            (preview.execution_id,),
        ).fetchone()[0]
    with open(stored_path, "ab") as stream:
        stream.write(b"changed")
    with pytest.raises(OpportunityImportValidationError, match="cambió"):
        OpportunityImportService.confirm(
            preview.execution_id, confirmed=True, executed_by="tester"
        )
