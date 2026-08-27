import sqlite3
import inspect

import pytest
from flask import Flask

from app.database.migrations import upgrade
from app.routes import register_blueprints
from app.workspace.services.commercial_approval_service import CommercialApprovalService
from app.workspace.constants.activity_types import ActivityType
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.services.project_workspace_service import ProjectWorkspaceService
from app.workspace.services.opportunity_timeline_service import OpportunityTimelineService


@pytest.fixture
def approval_database(tmp_path, monkeypatch):
    path = tmp_path / "approvals.db"
    monkeypatch.setattr("app.database.connection.DB_PATH", path)
    upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO ws_customers(id,name,erp_customer_id) VALUES (1,'Cliente Uno','9001')")
        connection.execute("""INSERT INTO ws_projects(
            id,customer_id,name,status,objective,sales_rep
        ) VALUES (1,1,'Expansión','negotiation','Crecer','Ana')""")
    return path


def _request(discount=10):
    return {
        "manufacturer": "SKF", "product_family": "Rodamientos",
        "product": "6201", "quantity": "100", "opportunity_value": "50000000",
        "probability": "70", "list_price": "100", "requested_price": "90",
        "requested_discount": str(discount), "estimated_margin": "18",
        "expected_revenue": "45000000", "currency": "COP",
        "reason_code": "competition", "justification": "Competidor con precio inferior",
        "competitor": "Competidor A", "competitor_price": "88",
        "commercial_impact": "Alto", "business_notes": "Cuenta en crecimiento",
    }


def test_complete_approval_lifecycle_is_auditable(approval_database):
    approval_id = CommercialApprovalService.create(1, _request(), actor="vendedor")
    CommercialApprovalService.submit(approval_id, actor="vendedor")
    CommercialApprovalService.decide(
        approval_id, decision="approved", approver="Ricardo Lugo",
        comments="Aprobado por volumen", approved_discount=8,
        expiration_date="2026-12-31", role="approver",
    )

    detail = CommercialApprovalService.get_detail(approval_id)

    assert detail["approval"]["status"] == "approved"
    assert [event["to_status"] for event in detail["history"]] == [
        "draft", "submitted", "pending_approval", "approved",
    ]
    assert detail["decisions"][0]["approved_discount"] == 8
    assert detail["decisions"][0]["approved_unit_price"] == "92.00"
    assert detail["decisions"][0]["approved_total_amount"] == "9200.00"


def test_returned_request_can_be_edited_and_resubmitted(approval_database):
    approval_id = CommercialApprovalService.create(1, _request(10), actor="vendedor")
    CommercialApprovalService.submit(approval_id, actor="vendedor")
    CommercialApprovalService.decide(
        approval_id, decision="returned", approver="Ricardo Lugo",
        comments="Ajustar descuento", approved_discount=None,
        expiration_date=None, role="approver",
    )
    CommercialApprovalService.update(approval_id, _request(6), actor="vendedor")
    CommercialApprovalService.submit(approval_id, actor="vendedor")

    assert CommercialApprovalService.get_detail(approval_id)["approval"]["status"] == "pending_approval"


def test_only_approvers_can_decide_and_illegal_transitions_fail(approval_database):
    approval_id = CommercialApprovalService.create(1, _request(), actor="vendedor")
    with pytest.raises(ValueError, match="pendiente"):
        CommercialApprovalService.decide(
            approval_id,decision="approved",approver="usuario",comments="Sí",
            approved_discount=10,expiration_date=None,role="approver")
    CommercialApprovalService.submit(approval_id, actor="vendedor")
    with pytest.raises(PermissionError, match="autorización"):
        CommercialApprovalService.decide(
            approval_id,decision="approved",approver="usuario",comments="Sí",
            approved_discount=10,expiration_date=None,role="user")


def test_multiple_requests_are_preserved(approval_database):
    first = CommercialApprovalService.create(1, _request(10), actor="vendedor")
    second = CommercialApprovalService.create(1, _request(6), actor="vendedor")
    page = CommercialApprovalService.get_page(1)

    assert first != second
    assert page["pagination"]["total"] == 2
    assert {item["requested_discount"] for item in page["approvals"]} == {10, 6}


@pytest.mark.parametrize(("discount", "quantity", "unit", "total"), [
    ("0", "1", "100.00", "100.00"),
    ("15", "2", "85.00", "170.00"),
    ("12.3456", "3.5", "87.65", "306.78"),
])
def test_decimal_calculation_and_rounding(discount, quantity, unit, total):
    result = CommercialApprovalService.calculate_approved_values(
        list_unit_price="100", approved_discount_percent=discount,
        quantity=quantity, currency="COP", requested_discount_percent="10")
    assert result["approved_unit_price"] == unit
    assert result["approved_total_amount"] == total


@pytest.mark.parametrize(("field", "value", "message"), [
    ("approved_discount_percent", "-1", "entre 0% y 100%"),
    ("approved_discount_percent", "101", "entre 0% y 100%"),
    ("approved_discount_percent", "1.12345", "cuatro decimales"),
    ("quantity", "0", "mayor que cero"),
    ("list_unit_price", "", "precio de lista válido"),
])
def test_invalid_monetary_inputs_are_rejected(field, value, message):
    values = dict(list_unit_price="100", approved_discount_percent="10",
                  quantity="1", currency="COP")
    values[field] = value
    with pytest.raises(ValueError, match=message):
        CommercialApprovalService.calculate_approved_values(**values)


def _project(path):
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return dict(connection.execute(
            "SELECT * FROM ws_projects WHERE id=1").fetchone())


def _timeline(path):
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(
            "SELECT * FROM ws_activities ORDER BY id").fetchall()]


def _approve(discount, *, actor="Ricardo Lugo"):
    approval_id = CommercialApprovalService.create(1, _request(discount), actor="vendedor")
    CommercialApprovalService.submit(approval_id, actor="vendedor")
    CommercialApprovalService.decide(
        approval_id, decision="approved", approver=actor,
        comments="Aprobado", approved_discount=str(discount),
        expiration_date=None, role="approver")
    return approval_id


def test_approval_atomically_updates_canonical_opportunity_amount(approval_database):
    approval_id = _approve(15)
    assert _project(approval_database)["commercial_amount"] == "8500.00"
    history = CommercialApprovalService.get_detail(approval_id)["history"][-1]
    assert '"opportunity_amount_before": null' in history["event_data"]
    assert '"opportunity_amount_after": "8500.00"' in history["event_data"]


def test_workspace_reads_the_canonical_approved_opportunity_amount(
    approval_database,
):
    _approve(15)

    project = ProjectRepository.get_project(1)
    workspace = ProjectWorkspaceService.get_workspace(1)

    assert project["commercial_amount"] == "8500.00"
    assert project["commercial_currency"] == "COP"
    assert workspace["dashboard"].commercial_value["display"] == (
        "COP 8,500.00"
    )
    assert workspace["commercial_approval"]["approved_total_amount"] == (
        "8500.00"
    )


@pytest.mark.parametrize("decision", ["rejected", "returned"])
def test_non_approval_decisions_do_not_change_amount(approval_database, decision):
    approval_id = CommercialApprovalService.create(1, _request(), actor="vendedor")
    CommercialApprovalService.submit(approval_id, actor="vendedor")
    CommercialApprovalService.decide(
        approval_id, decision=decision, approver="Ricardo Lugo",
        comments="No aprobado", approved_discount=None,
        expiration_date=None, role="approver")
    assert _project(approval_database)["commercial_amount"] is None


def test_opportunity_update_failure_rolls_back_decision_status_and_history(approval_database, monkeypatch):
    approval_id = CommercialApprovalService.create(1, _request(), actor="vendedor")
    CommercialApprovalService.submit(approval_id, actor="vendedor")
    monkeypatch.setattr(
        "app.workspace.services.commercial_approval_service.ProjectRepository.update_commercial_amount",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fallo")))
    with pytest.raises(RuntimeError, match="fallo"):
        CommercialApprovalService.decide(
            approval_id, decision="approved", approver="Ricardo Lugo",
            comments="Aprobado", approved_discount="10",
            expiration_date=None, role="approver")
    detail = CommercialApprovalService.get_detail(approval_id)
    assert detail["approval"]["status"] == "pending_approval"
    assert detail["decisions"] == []
    assert detail["history"][-1]["to_status"] == "pending_approval"
    assert _project(approval_database)["commercial_amount"] is None


def test_latest_approval_overwrites_amount_and_preserves_history(approval_database):
    first = _approve(10)
    second = _approve(20)
    assert _project(approval_database)["commercial_amount"] == "8000.00"
    assert CommercialApprovalService.get_detail(first)["decisions"][0]["approved_total_amount"] == "9000.00"
    assert CommercialApprovalService.get_detail(second)["decisions"][0]["approved_total_amount"] == "8000.00"


def test_approval_replaces_existing_opportunity_amount(approval_database):
    with sqlite3.connect(approval_database) as connection:
        connection.execute("""UPDATE ws_projects SET
            commercial_amount='12500.00',commercial_currency='COP' WHERE id=1""")
    approval_id = _approve(15)
    assert _project(approval_database)["commercial_amount"] == "8500.00"
    history = CommercialApprovalService.get_detail(approval_id)["history"][-1]
    assert '"opportunity_amount_before": "12500.00"' in history["event_data"]


def test_request_keeps_immutable_erp_price_snapshot(approval_database):
    request_data = _request()
    request_data.update(product_reference="ERP-6201", erp_price_source="ERP-LH",
                        erp_price_retrieved_at="2026-07-21T09:30:00")
    approval_id = CommercialApprovalService.create(1, request_data, actor="vendedor")
    request_data["list_price"] = "999"
    approval = CommercialApprovalService.get_detail(approval_id)["approval"]
    assert approval["list_price"] == 100
    assert approval["product_reference"] == "ERP-6201"
    assert approval["erp_price_source"] == "ERP-LH"
    assert approval["erp_price_retrieved_at"] == "2026-07-21T09:30:00"


def test_cancel_does_not_update_opportunity_amount(approval_database):
    approval_id = CommercialApprovalService.create(1, _request(), actor="vendedor")
    CommercialApprovalService.cancel(
        approval_id, actor="vendedor", comments="Ya no se requiere")
    assert _project(approval_database)["commercial_amount"] is None


def test_approval_service_has_no_quote_dependency():
    source = inspect.getsource(CommercialApprovalService)
    assert "QuoteRepository" not in source
    assert "ProjectQuoteRepository" not in source


def test_missing_list_price_blocks_approval_without_partial_changes(approval_database):
    request_data = _request()
    request_data["list_price"] = ""
    approval_id = CommercialApprovalService.create(1, request_data, actor="vendedor")
    CommercialApprovalService.submit(approval_id, actor="vendedor")
    with pytest.raises(ValueError, match="precio de lista válido"):
        CommercialApprovalService.decide(
            approval_id, decision="approved", approver="Ricardo Lugo",
            comments="Aprobado", approved_discount="10",
            expiration_date=None, role="approver")
    detail = CommercialApprovalService.get_detail(approval_id)
    assert detail["approval"]["status"] == "pending_approval"
    assert detail["decisions"] == []
    assert _project(approval_database)["commercial_amount"] is None


def test_approval_lifecycle_is_published_to_commercial_timeline(approval_database):
    approval_id = _approve(12)
    events = _timeline(approval_database)
    assert [event["activity_type"] for event in events] == [
        ActivityType.APPROVAL_CREATED,
        ActivityType.APPROVAL_SUBMITTED,
        ActivityType.APPROVAL_APPROVED,
    ]
    assert all(event["activity_type"] in ActivityType.COMMERCIAL_APPROVAL_TYPES
               for event in events)
    approved = events[-1]
    assert "Descuento comercial aprobado" == approved["title"]
    assert f"AP-{approval_id:06d}" in approved["details"]
    assert "Descuento solicitado: 12,00%" in approved["details"]
    assert "Precio de lista: COP 100.00" in approved["details"]
    assert "Precio final aprobado: COP 88.00" in approved["details"]
    assert "Nuevo monto: COP 8,800.00" in approved["details"]
    assert "Monto anterior: Sin monto registrado" in approved["details"]
    presented = OpportunityTimelineService.present(approved)
    assert presented["approval_id"] == approval_id
    assert presented["timeline_icon"] == "check"


@pytest.mark.parametrize(("decision", "activity_type", "title"), [
    ("returned", ActivityType.APPROVAL_RETURNED, "Aprobación comercial devuelta"),
    ("rejected", ActivityType.APPROVAL_REJECTED, "Aprobación comercial rechazada"),
])
def test_non_approval_decisions_publish_their_timeline_event(
        approval_database, decision, activity_type, title):
    approval_id = CommercialApprovalService.create(1, _request(), actor="vendedor")
    CommercialApprovalService.submit(approval_id, actor="vendedor")
    CommercialApprovalService.decide(
        approval_id, decision=decision, approver="Ricardo Lugo",
        comments="Revisar condiciones", approved_discount=None,
        expiration_date=None, role="approver")
    event = _timeline(approval_database)[-1]
    assert event["activity_type"] == activity_type
    assert event["title"] == title
    assert "Revisar condiciones" in event["details"]


def test_cancel_publishes_once_and_failed_retry_does_not_duplicate(approval_database):
    approval_id = CommercialApprovalService.create(1, _request(), actor="vendedor")
    CommercialApprovalService.cancel(
        approval_id, actor="vendedor", comments="Cliente retiró la solicitud")
    with pytest.raises(ValueError):
        CommercialApprovalService.cancel(
            approval_id, actor="vendedor", comments="Segundo intento")
    events = _timeline(approval_database)
    assert [event["activity_type"] for event in events].count(
        ActivityType.APPROVAL_CANCELLED) == 1


def test_only_named_approver_can_approve(approval_database):
    approval_id = CommercialApprovalService.create(1, _request(), actor="vendedor")
    CommercialApprovalService.submit(approval_id, actor="vendedor")
    with pytest.raises(PermissionError, match="Ricardo Lugo"):
        CommercialApprovalService.decide(
            approval_id, decision="approved", approver="Otro Gerente",
            comments="Aprobado", approved_discount="10",
            expiration_date=None, role="approver")


def test_route_ignores_manipulated_calculated_values_and_renders_result(approval_database):
    approval_id = CommercialApprovalService.create(1, _request(), actor="vendedor")
    CommercialApprovalService.submit(approval_id, actor="vendedor")
    application = Flask(__name__, template_folder="../app/templates",
                        static_folder="../app/static")
    register_blueprints(application)
    client = application.test_client()
    pending = client.get(f"/workspace/approvals/{approval_id}")
    assert b"Decisi\xc3\xb3n de Ricardo Lugo" in pending.data
    assert b'name="approved_discount"' in pending.data
    assert b'value="approved"' in pending.data
    response = client.post(
        f"/workspace/approvals/{approval_id}/decision",
        data={"decision":"approved", "approved_discount":"15",
              "approved_unit_price":"1", "approved_total_amount":"1",
              "comments":"Aprobado"})
    assert response.status_code == 302
    decision = CommercialApprovalService.get_detail(approval_id)["decisions"][0]
    assert decision["approved_unit_price"] == "85.00"
    assert decision["approved_total_amount"] == "8500.00"
    rendered = client.get(f"/workspace/approvals/{approval_id}")
    assert rendered.status_code == 200
    assert b"8500.00" in rendered.data
    assert b"Ricardo Lugo" in rendered.data
    assert b'name="approved_discount"' not in rendered.data


def test_rejected_request_shows_final_decision_without_panel(approval_database):
    approval_id = CommercialApprovalService.create(1, _request(), actor="vendedor")
    CommercialApprovalService.submit(approval_id, actor="vendedor")
    application = Flask(__name__, template_folder="../app/templates",
                        static_folder="../app/static")
    register_blueprints(application)
    client = application.test_client()
    response = client.post(f"/workspace/approvals/{approval_id}/decision", data={
        "decision":"rejected", "approved_discount":"10",
        "comments":"Condiciones no autorizadas"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Rechazada" in response.data
    assert b"Condiciones no autorizadas" in response.data
    assert b'name="approved_discount"' not in response.data
