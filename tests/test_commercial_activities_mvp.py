import sqlite3

import pytest

from app.database.migrations import upgrade
from app.workspace.repositories.activity_repository import ActivityRepository
from app.workspace.services.commercial_activity_service import (
    CommercialActivityService,
)


@pytest.fixture
def activity_database(tmp_path, monkeypatch):
    path = tmp_path / "activities.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    monkeypatch.setattr(
        CommercialActivityService, "EVIDENCE_ROOT", tmp_path / "evidence"
    )
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO ws_customers (id, name) VALUES (1, 'Cliente Uno')"
        )
        connection.execute(
            "INSERT INTO ws_customers (id, name) VALUES (2, 'Cliente Dos')"
        )
        connection.execute(
            """INSERT INTO ws_projects (
                id, customer_id, name, objective
            ) VALUES (10, 1, 'Oportunidad', 'Crecer')"""
        )
    return path


def _values(**overrides):
    values = {
        "customer_id": 1,
        "activity_type": "meeting",
        "purpose": "Revisión comercial",
        "summary": "Se revisaron necesidades del cliente.",
        "occurred_at": "2026-07-23T10:30",
        "participant_user_ids": [],
        "results": ["followup_required"],
    }
    values.update(overrides)
    return values


def test_activity_can_exist_for_customer_without_opportunity(activity_database):
    result = CommercialActivityService.create(
        values=_values(), evidence_files=[]
    )
    activities = ActivityRepository.list_customer_activities(1)

    assert result.project_id is None
    assert activities[0]["summary"] == "Se revisaron necesidades del cliente."
    assert activities[0]["customer_id"] == 1


def test_activity_rejects_opportunity_from_another_customer(activity_database):
    with pytest.raises(ValueError, match="no pertenece"):
        CommercialActivityService.create(
            values=_values(customer_id=2, project_id=10),
            evidence_files=[],
        )


def test_supplier_name_is_conditional(activity_database):
    with pytest.raises(ValueError, match="proveedor"):
        CommercialActivityService.create(
            values=_values(supplier_participated=True),
            evidence_files=[],
        )


def test_potential_value_requires_currency(activity_database):
    with pytest.raises(ValueError, match="moneda"):
        CommercialActivityService.create(
            values=_values(potential_value="1000", currency_code=""),
            evidence_files=[],
        )
