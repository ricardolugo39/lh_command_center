import io
import json
import sqlite3

import pandas as pd
import pytest
from werkzeug.datastructures import FileStorage

from app.database.migrations import upgrade
from app.workspace.repositories.opportunity_import_repository import (
    OpportunityImportRepository,
)
from app.workspace.services.opportunity_import_profile_service import (
    OpportunityImportProfileService,
)
from app.workspace.services.opportunity_import_service import (
    OpportunityImportService,
)


HEADERS = [
    "ID", "Fecha", "Prioridad", "Oportunidad", "Nombre Empresa", "Marca",
    "Código producto", "Descripción producto", "Valor Potencial",
    "Sucursal empresa", "Documento", "Probabilidad", "Fecha Cierre",
    "Vendedor", "Creado por", "Estado", "Etapa", "Teléfono", "Móvil",
    "Ciudad",
]


@pytest.fixture
def production_database(tmp_path, monkeypatch):
    path = tmp_path / "production-crm.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    monkeypatch.setattr(
        OpportunityImportService, "STORAGE_ROOT", tmp_path / "retained"
    )
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE raw_customers (
                nit TEXT, razonsocial TEXT, ciudad TEXT, telefono1 TEXT,
                movil TEXT, vendedor TEXT
            );
            CREATE TABLE dim_customer (
                customer_site_id TEXT, customer_id TEXT,
                customer_name TEXT, city TEXT, seller TEXT
            );
            """
        )
        connection.executemany(
            "INSERT INTO ws_customers(id,name,erp_customer_id) VALUES (?,?,?)",
            [
                (1, "ACME S.A.S.", "9001"),
                (2, "Duplicada Norte S.A.", "9002"),
                (3, "Duplicada Sur S.A.", "9003"),
            ],
        )
        connection.executemany(
            """INSERT INTO raw_customers(
                nit,razonsocial,ciudad,telefono1,movil,vendedor
            ) VALUES (?,?,?,?,?,?)""",
            [
                ("9001", "ACME S.A.S.", "Cali", "6021111111", None, "ANA VENDEDORA"),
                ("9002", "EMPRESA DUPLICADA", "Bogotá", "6012222222", None, "ANA VENDEDORA"),
                ("9003", "EMPRESA DUPLICADA", "Cali", "6023333333", None, "ANA VENDEDORA"),
            ],
        )
        connection.execute(
            """INSERT INTO dim_customer(
                customer_site_id,customer_id,customer_name,city,seller
            ) VALUES ('S1','9001','ACME S.A.S.','Cali','ANA VENDEDORA')"""
        )
    return path


def _row(
    opportunity="642", company="ACME S.A.S.", *,
    row_id="1001", value=1000, brand="SKF", code="6204",
    seller="ANA VENDEDORA", status="Abierto",
):
    values = {
        "ID": row_id, "Fecha": "2026-07-01", "Prioridad": 2,
        "Oportunidad": opportunity, "Nombre Empresa": company,
        "Marca": brand, "Código producto": code,
        "Descripción producto": "RODAMIENTO RIGIDO",
        "Valor Potencial": value, "Sucursal empresa": 1,
        "Documento": f"PCT{opportunity}", "Probabilidad": 50,
        "Fecha Cierre": "2026-08-15", "Vendedor": seller,
        "Creado por": "ANA", "Estado": status,
        "Etapa": "Propuesta o Cotizacion", "Teléfono": "6021111111",
        "Móvil": None, "Ciudad": "Cali",
    }
    return values


def _upload(rows, *, sheet_name="Datos"):
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        pd.DataFrame(rows, columns=HEADERS).to_excel(
            writer, sheet_name=sheet_name, index=False
        )
    stream.seek(0)
    return FileStorage(stream=stream, filename="crm.xlsx")


def test_production_profile_maps_real_headers_and_sheet(production_database):
    profile = OpportunityImportProfileService.active_profile()
    assert profile["profile_name"] == "CRM Producción · export Oportunidades"
    assert profile["grouping_configuration"]["sheet_name"] == "Datos"
    assert profile["column_mapping"]["external_opportunity_id"] == "Oportunidad"
    assert profile["column_mapping"]["source_row_id"] == "ID"
    assert profile["column_mapping"]["line_potential_value"] == "Valor Potencial"


def test_product_rows_group_and_duplicate_value_is_not_double_counted(
    production_database,
):
    first = _row()
    second = _row(row_id="1002", value=2000, brand="NTN", code="6305")
    preview = OpportunityImportService.prepare(
        upload=_upload([first, second, second]), executed_by="tester"
    )
    group = preview.groups[0]
    assert preview.rows_read == 3
    assert preview.metrics["groups_identified"] == 1
    assert group["source_row_numbers"] == [2, 3, 4]
    assert group["source_row_ids"] == ["1001", "1002"]
    assert group["product_line_count"] == 2
    assert group["total_potential_value"] == 3000
    assert group["brands"] == ["NTN", "SKF"]
    assert group["canonical"]["opportunity_name"].startswith("NTN / SKF")
    assert group["canonical"]["source_updated_at"] == "2026-07-01"
    assert group["canonical"]["stage"] == "quoting"


@pytest.mark.parametrize(
    ("crm_status", "crm_stage", "expected"),
    [
        ("Abierto", "Contacto", "prospect"),
        ("Abierto", "Propuesta o Cotización", "quoting"),
        ("Abierto", "Negociación", "negotiation"),
        ("Realizado", "Propuesta o Cotizacion", "won"),
        ("Cancelado", "Contacto", "cancelled"),
    ],
)
def test_crm_lifecycle_is_normalized(crm_status, crm_stage, expected):
    assert OpportunityImportService._map_crm_lifecycle(
        crm_status, crm_stage
    ) == expected


def test_customer_resolution_is_explainable_and_conservative(
    production_database,
):
    exact = OpportunityImportService.prepare(
        upload=_upload([_row()]), executed_by="tester"
    ).groups[0]
    assert exact["customer_id"] == 1
    assert exact["customer_match_reason"] == "exact_normalized_name"

    city_row = _row(opportunity="643", company="EMPRESA DUPLICADA")
    city = OpportunityImportService.prepare(
        upload=_upload([city_row]), executed_by="tester"
    ).groups[0]
    assert city["customer_id"] == 3
    assert city["customer_match_reason"] == "exact_name_and_city"

    ambiguous_row = _row(opportunity="644", company="EMPRESA DUPLICADA")
    ambiguous_row["Ciudad"] = None
    ambiguous_row["Teléfono"] = None
    ambiguous = OpportunityImportService.prepare(
        upload=_upload([ambiguous_row]), executed_by="tester"
    ).groups[0]
    assert ambiguous["action"] == "needs_review"
    assert len(ambiguous["customer_match_candidates"]) == 2

    missing = _row(opportunity="645", company=None)
    blocked = OpportunityImportService.prepare(
        upload=_upload([missing]), executed_by="tester"
    ).groups[0]
    assert blocked["action"] == "blocked"


def test_customer_and_seller_resolutions_are_reused_as_aliases(
    production_database,
):
    row = _row(company="ACME PLANTA ESPECIAL", seller="ASESOR CRM")
    preview = OpportunityImportService.prepare(
        upload=_upload([row]), executed_by="tester"
    )
    assert preview.groups[0]["action"] == "needs_review"
    assert preview.groups[0]["seller_resolution_status"] == "needs_review"
    OpportunityImportService.resolve_customer(
        preview.execution_id, "642", customer_id=1, resolved_by="reviewer"
    )
    OpportunityImportService.resolve_seller(
        preview.execution_id, "642",
        sales_rep="ANA VENDEDORA", resolved_by="reviewer",
    )

    later = OpportunityImportService.prepare(
        upload=_upload([row]), executed_by="tester"
    ).groups[0]
    assert later["customer_id"] == 1
    assert later["customer_match_reason"] == "confirmed_customer_alias"
    assert later["resolved_sales_rep"] == "ANA VENDEDORA"
    assert later["seller_match_reason"] == "confirmed_seller_alias"


def test_create_reimport_and_changed_source_facts_update_in_place(
    production_database,
):
    preview = OpportunityImportService.prepare(
        upload=_upload([_row()]), executed_by="tester"
    )
    OpportunityImportService.confirm(
        preview.execution_id, confirmed=True, executed_by="tester"
    )
    same = OpportunityImportService.prepare(
        upload=_upload([_row()]), executed_by="tester"
    )
    assert same.groups[0]["action"] == "unchanged"

    changed_row = _row(value=9000, status="Realizado")
    changed = OpportunityImportService.prepare(
        upload=_upload([changed_row]), executed_by="tester"
    )
    assert changed.groups[0]["action"] == "update"
    OpportunityImportService.confirm(
        changed.execution_id, confirmed=True, executed_by="tester"
    )
    with sqlite3.connect(production_database) as connection:
        connection.row_factory = sqlite3.Row
        projects = connection.execute(
            "SELECT * FROM ws_projects WHERE origin='crm'"
        ).fetchall()
    assert len(projects) == 1
    metadata = json.loads(projects[0]["import_metadata"])
    assert metadata["source_facts"]["potential_value"] == 9000
    assert metadata["source_facts"]["crm_status"] == "Realizado"
    assert projects[0]["commercial_amount"] is None
    assert projects[0]["closed_at"] is None


def test_absence_does_not_delete_and_local_closure_blocks_reimport(
    production_database,
):
    first = OpportunityImportService.prepare(
        upload=_upload([_row("642"), _row("700", row_id="2001")]),
        executed_by="tester",
    )
    OpportunityImportService.confirm(
        first.execution_id, confirmed=True, executed_by="tester"
    )
    with sqlite3.connect(production_database) as connection:
        connection.execute(
            "UPDATE ws_projects SET status='won',closed_at='2026-07-20' "
            "WHERE external_id='642'"
        )
    later = OpportunityImportService.prepare(
        upload=_upload([_row("642")]), executed_by="tester"
    )
    assert later.groups[0]["action"] == "blocked"
    with sqlite3.connect(production_database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM ws_projects WHERE external_id='700'"
        ).fetchone()[0] == 1


def test_partial_confirmation_imports_ready_and_persists_exceptions(
    production_database,
):
    unmatched = _row("700", company="CLIENTE SIN COINCIDENCIA", row_id="2")
    missing = _row("701", company=None, row_id="3")
    preview = OpportunityImportService.prepare(
        upload=_upload([_row("642"), unmatched, missing]),
        executed_by="tester",
    )
    assert preview.metrics["groups_eligible"] == 1
    assert preview.metrics["groups_deferred"] == 2
    assert preview.can_confirm

    result = OpportunityImportService.confirm(
        preview.execution_id, confirmed=True, executed_by="tester"
    )
    assert result["status"] == "completed"
    assert result["rows_inserted"] == 1
    assert result["groups_deferred"] == 2
    with sqlite3.connect(production_database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM ws_projects WHERE origin='crm'"
        ).fetchone()[0] == 1
        statuses = connection.execute(
            "SELECT resolution_status FROM crm_opportunity_pending ORDER BY id"
        ).fetchall()
    assert statuses == [("needs_review",), ("blocked",)]


def test_pending_resolution_and_import_reuses_original_file(
    production_database,
):
    unmatched = _row(company="CLIENTE ALIAS")
    preview = OpportunityImportService.prepare(
        upload=_upload([unmatched]), executed_by="tester"
    )
    OpportunityImportService.confirm(
        preview.execution_id, confirmed=True, executed_by="tester"
    )
    pending = OpportunityImportService.pending_queue()[0]
    OpportunityImportService.resolve_pending_customer(
        pending["id"], customer_id=1, apply_to_company=False,
        resolved_by="reviewer",
    )

    result = OpportunityImportService.import_resolved_pending(
        pending_ids=[pending["id"]], executed_by="reviewer"
    )
    assert result["created"] == 1
    assert len(result["execution_ids"]) == 1
    with sqlite3.connect(production_database) as connection:
        connection.row_factory = sqlite3.Row
        project = connection.execute(
            "SELECT * FROM ws_projects WHERE external_id='642'"
        ).fetchone()
        pending_row = connection.execute(
            "SELECT * FROM crm_opportunity_pending WHERE id=?",
            (pending["id"],),
        ).fetchone()
        history = connection.execute(
            """SELECT event_type FROM crm_opportunity_pending_history
            WHERE pending_id=? ORDER BY id""",
            (pending["id"],),
        ).fetchall()
    assert project["customer_id"] == 1
    assert pending_row["resolution_status"] == "imported"
    assert pending_row["original_import_execution_id"] == preview.execution_id
    assert pending_row["imported_import_execution_id"] == result["execution_ids"][0]
    assert [row[0] for row in history] == [
        "deferred", "customer_resolved", "opportunity_imported"
    ]


def test_bulk_company_resolution_and_no_duplicate_pending_on_refresh(
    production_database,
):
    rows = [
        _row("700", company="MISMA EMPRESA CRM", row_id="1", value=100),
        _row("701", company="MISMA EMPRESA CRM", row_id="2", value=200),
    ]
    first = OpportunityImportService.prepare(
        upload=_upload(rows), executed_by="tester"
    )
    OpportunityImportService.confirm(
        first.execution_id, confirmed=True, executed_by="tester"
    )
    pending = OpportunityImportService.pending_queue()
    assert len(pending) == 2
    resolved = OpportunityImportService.resolve_pending_customer(
        pending[0]["id"], customer_id=1, apply_to_company=True,
        resolved_by="reviewer",
    )
    assert resolved == 2
    assert all(
        item["resolution_status"] == "ready"
        for item in OpportunityImportService.pending_queue()
    )

    rows[0]["Valor Potencial"] = 999
    second = OpportunityImportService.prepare(
        upload=_upload(rows), executed_by="tester"
    )
    assert second.metrics["groups_eligible"] == 2
    OpportunityImportService.confirm(
        second.execution_id, confirmed=True, executed_by="tester"
    )
    with sqlite3.connect(production_database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM crm_opportunity_pending"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM ws_projects WHERE origin='crm'"
        ).fetchone()[0] == 2
        metadata = connection.execute(
            "SELECT import_metadata FROM ws_projects WHERE external_id='700'"
        ).fetchone()[0]
    assert json.loads(metadata)["source_facts"]["potential_value"] == 999
