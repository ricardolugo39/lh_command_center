import sqlite3

import pytest

from app import create_app
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
        "finding_type": "none",
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


def test_activity_can_create_contact_inline(activity_database):
    result = CommercialActivityService.create(
        values=_values(
            contact_id="__new__",
            new_contact_name="Ana Compras",
            new_contact_job_title="Jefe de compras",
        ),
        evidence_files=[],
    )
    with sqlite3.connect(activity_database) as connection:
        row = connection.execute(
            """SELECT c.full_name,c.job_title FROM ws_activities a
            JOIN contacts c ON c.id=a.contact_id WHERE a.id=?""",
            (result.activity_id,),
        ).fetchone()
    assert row == ("Ana Compras", "Jefe de compras")


def test_activity_preserves_structured_finding_and_engineering(activity_database):
    result = CommercialActivityService.create(
        values=_values(
            finding_type="risk",
            finding_detail="Competidor instalado",
            engineering_participants="Andrea Pérez",
        ),
        evidence_files=[],
    )
    with sqlite3.connect(activity_database) as connection:
        row = connection.execute(
            """SELECT finding_type,finding_detail,engineering_participants,
                identified_risk FROM ws_activities WHERE id=?""",
            (result.activity_id,),
        ).fetchone()
    assert row == (
        "risk", "Competidor instalado", "Andrea Pérez", "Competidor instalado"
    )


def test_potential_value_requires_currency(activity_database):
    with pytest.raises(ValueError, match="moneda"):
        CommercialActivityService.create(
            values=_values(potential_value="1000", currency_code=""),
            evidence_files=[],
        )


def test_existing_opportunity_choice_requires_customer_opportunity(activity_database):
    with pytest.raises(ValueError, match="oportunidad existente"):
        CommercialActivityService.create(
            values=_values(opportunity_relation="existing"),
            evidence_files=[],
        )


def test_no_opportunity_requires_reason_and_preserves_pilot_provenance(
    activity_database,
):
    with pytest.raises(ValueError, match="por qué"):
        CommercialActivityService.create(
            values=_values(opportunity_relation="none"),
            evidence_files=[],
        )
    result = CommercialActivityService.create(
        values=_values(
            opportunity_relation="none",
            opportunity_link_reason="Capacitación",
            rollout_phase="pilot",
        ),
        evidence_files=[],
    )
    with sqlite3.connect(activity_database) as connection:
        row = connection.execute(
            """SELECT rollout_phase,opportunity_link_reason
            FROM ws_activities WHERE id=?""",
            (result.activity_id,),
        ).fetchone()
    assert row == ("pilot", "Capacitación")


def test_limited_pilot_user_only_reaches_activity_capture(activity_database):
    with sqlite3.connect(activity_database) as connection:
        connection.execute(
            """INSERT INTO ws_users (
                id,display_name,email,email_normalized,role,is_active,
                office,erp_sales_rep_name,module_access_mode
            ) VALUES (20,'Asesor Piloto','piloto@lugohermanos.com',
                'piloto@lugohermanos.com','advisor',1,'Cali',
                'Asesor Piloto','limited')"""
        )
        connection.execute(
            """INSERT INTO user_module_permissions(user_id,module_key)
            VALUES (20,'activities')"""
        )
        connection.execute(
            """INSERT INTO ws_customer_portfolio_metadata(
                erp_customer_id,advisor,office
            ) VALUES ('ERP-1','Asesor Piloto','Cali')"""
        )
        connection.execute(
            "UPDATE ws_customers SET erp_customer_id='ERP-1' WHERE id=1"
        )
    application = create_app({
        "TESTING": True,
        "TEST_AUTH_BYPASS": True,
        "TEST_AUTH_USER_ID": 20,
    }, run_migrations=False)
    client = application.test_client()
    home = client.get("/")
    assert home.status_code == 302
    assert home.headers["Location"].endswith("/activities/")
    assert client.get("/workspace/projects").status_code == 403
    capture = client.get("/activities/")
    assert capture.status_code == 200
    assert b"Cliente Uno" not in capture.data
    assert client.get("/activities/customer-search?q=C").get_json() == []
    customer_results = client.get(
        "/activities/customer-search?q=Cliente"
    ).get_json()
    assert [row["name"] for row in customer_results] == ["Cliente Uno"]
    assert customer_results[0]["activity_url"].endswith(
        "/activities/customer/1/new"
    )
    assert client.get("/activities/customer/1/new").status_code == 200
    assert client.get("/activities/customer/2/new").status_code == 403
    assert client.get("/activities/training/report").status_code == 403


def test_training_completion_is_tied_to_authenticated_user(activity_database):
    with sqlite3.connect(activity_database) as connection:
        connection.execute(
            """INSERT INTO ws_users (
                id,display_name,email,email_normalized,role,is_active,
                office,module_access_mode
            ) VALUES (21,'Vendedora Bogotá','ventas@lugohermanos.com',
                'ventas@lugohermanos.com','advisor',1,'Bogotá','limited')"""
        )
        connection.execute(
            """INSERT INTO user_module_permissions(user_id,module_key)
            VALUES (21,'activities')"""
        )
    application = create_app({
        "TESTING": True,
        "TEST_AUTH_BYPASS": True,
        "TEST_AUTH_USER_ID": 21,
    }, run_migrations=False)
    client = application.test_client()

    assert client.get("/activities/training").status_code == 200
    with client.session_transaction() as session:
        completion_token = session["activity_training_token"]
    response = client.post("/activities/training", data={
        "completion_token": completion_token,
        "completed_steps": "7",
    })

    assert response.status_code == 302
    with sqlite3.connect(activity_database) as connection:
        row = connection.execute(
            """SELECT user_id,completed_at,attempt_count
            FROM activity_training_completions WHERE user_id=21"""
        ).fetchone()
    assert row[0] == 21
    assert row[1]
    assert row[2] == 1


def test_training_cannot_be_completed_without_finishing_steps(activity_database):
    application = create_app({
        "TESTING": True,
        "TEST_AUTH_BYPASS": True,
    }, run_migrations=False)
    client = application.test_client()
    client.get("/activities/training")
    with client.session_transaction() as session:
        completion_token = session["activity_training_token"]

    response = client.post("/activities/training", data={
        "completion_token": completion_token,
        "completed_steps": "1",
    })

    assert response.status_code == 400
