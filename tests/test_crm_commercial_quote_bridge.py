import sqlite3

import pytest

from app.database.migrations import upgrade
from app.workspace.repositories.customer_repository import CustomerRepository
from app.workspace.repositories.imported_commercial_line_repository import (
    ImportedCommercialLineRepository,
)
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.repositories.quote_repository import QuoteRepository
from app.workspace.services.commercial_interest_quote_service import (
    CommercialInterestQuoteService,
)
from app.workspace.services.opportunity_list_service import OpportunityListService


@pytest.fixture
def bridge_database(tmp_path, monkeypatch):
    path = tmp_path / "bridge.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    upgrade()
    customer_id = CustomerRepository.create_customer("Cliente CRM")
    project_id = ProjectRepository.create_project(
        customer_id, "Oportunidad importada", "Atender interés comercial",
        origin="crm", external_id="OPP-42", origin_reference="PCT-42",
    )
    with sqlite3.connect(path) as connection:
        cursor = connection.execute(
            """INSERT INTO erp_import_executions(
                import_type,original_filename,stored_file_path,file_hash,
                schema_version,status,executed_by
            ) VALUES ('crm_opportunities','crm.xlsx','crm.xlsx','hash','1',
                      'completed','tester')"""
        )
        execution_id = cursor.lastrowid
    return project_id, execution_id


def _line(key="line-1", value=1000):
    return {
        "source_line_key": key,
        "brand": "SKF",
        "product_code": "6204",
        "product_description": "Rodamiento",
        "line_potential_value": value,
        "source_row_id": "ROW-1",
        "source_row_number": 2,
    }


def test_imported_lines_sync_without_duplicates(bridge_database):
    project_id, execution_id = bridge_database
    ImportedCommercialLineRepository.synchronize(
        project_id, external_opportunity_id="OPP-42",
        origin_reference="PCT-42", product_lines=[_line()],
        import_execution_id=execution_id,
    )
    ImportedCommercialLineRepository.synchronize(
        project_id, external_opportunity_id="OPP-42",
        origin_reference="PCT-42", product_lines=[_line(value=1500)],
        import_execution_id=execution_id,
    )
    lines = ImportedCommercialLineRepository.list_for_opportunity(project_id)
    assert len(lines) == 1
    assert lines[0]["potential_value"] == 1500
    assert lines[0]["crm_row_ids"] == ["ROW-1"]
    assert lines[0]["crm_row_numbers"] == [2]


def test_quote_versions_preserve_imported_evidence(bridge_database):
    project_id, execution_id = bridge_database
    ImportedCommercialLineRepository.synchronize(
        project_id, external_opportunity_id="OPP-42",
        origin_reference="PCT-42", product_lines=[_line()],
        import_execution_id=execution_id,
    )
    first_quote_id = CommercialInterestQuoteService.generate_quote(project_id)
    first_lines = CommercialInterestQuoteService.quote_lines(first_quote_id)
    assert QuoteRepository.get_quote(first_quote_id)["revision"] == 1
    assert first_lines[0]["imported_commercial_line_id"]

    CommercialInterestQuoteService.update_quote_line(
        first_lines[0]["id"], brand="SKF", part_number="6204",
        description="Rodamiento editado", quantity=2, unit_price=750,
    )
    assert QuoteRepository.get_quote(first_quote_id)["amount"] == 1500

    ImportedCommercialLineRepository.synchronize(
        project_id, external_opportunity_id="OPP-42",
        origin_reference="PCT-42", product_lines=[_line(value=2000)],
        import_execution_id=execution_id,
    )
    interest = CommercialInterestQuoteService.get_interest(project_id)
    assert interest["changed_since_quote"] is True
    assert CommercialInterestQuoteService.quote_lines(first_quote_id)[0][
        "description"
    ] == "Rodamiento editado"

    second_quote_id = CommercialInterestQuoteService.generate_quote(project_id)
    assert QuoteRepository.get_quote(second_quote_id)["revision"] == 2
    assert QuoteRepository.get_quote(second_quote_id)["amount"] == 2000


def test_commercial_value_hierarchy_includes_crm_fallback():
    opportunity = {"commercial_amount": None}
    crm = OpportunityListService.present_commercial_value(
        opportunity, None, 5000
    )
    quote = OpportunityListService.present_commercial_value(
        opportunity, {"display_amount": "COP 6,000", "display_quote_number": "Q1"},
        5000,
    )
    approved = OpportunityListService.present_commercial_value(
        {"commercial_amount": 7000, "commercial_currency": "COP"},
        {"display_amount": "COP 6,000"}, 5000,
    )
    assert crm["detail"] == "Potencial CRM · informativo"
    assert quote["display"] == "COP 6,000"
    assert approved["display"] == "COP 7,000.00"
