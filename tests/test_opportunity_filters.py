from unittest.mock import patch

from app.workspace.services.opportunity_list_service import (
    OpportunityFilters,
    OpportunityListService,
)
from app.workspace.services.project_health_service import ProjectHealthService


def _record(**overrides):
    record = {
        "id": 1,
        "status": "negotiation",
        "sales_rep": "Ana",
        "customer_name": "Cliente Uno",
        "origin": "manual",
        "quote_id": None,
        "has_overdue_followup": 0,
        "last_activity_at": None,
    }
    record.update(overrides)
    return record


def test_filters_are_normalized_and_invalid_choices_are_ignored():
    filters = OpportunityFilters.from_query(
        {
            "status": " invalid ",
            "sales_rep": " Ana ",
            "health": "unknown",
            "customer_name": " Cliente ",
            "origin": " crm ",
        }
    )

    assert filters.as_dict() == {
        "status": "",
        "sales_rep": "Ana",
        "health": "",
        "customer_name": "Cliente",
        "origin": "crm",
    }


def test_combined_filters_are_sent_to_repository_once():
    with (
        patch(
            "app.workspace.services.opportunity_list_service."
            "ProjectRepository.list_project_overviews",
            return_value=[_record()],
        ) as list_overviews,
        patch(
            "app.workspace.services.opportunity_list_service."
            "ProjectRepository.list_sales_representatives",
            return_value=["Ana"],
        ),
    ):
        page = OpportunityListService.get_page(
            {
                "status": "negotiation",
                "sales_rep": "Ana",
                "customer_name": "Cliente",
                "origin": "crm",
            }
        )

    list_overviews.assert_called_once_with(
        {
            "status": "negotiation",
            "sales_rep": "Ana",
            "customer_name": "Cliente",
            "origin": "crm",
        }
    )
    assert len(page["opportunities"]) == 1
    assert page["has_active_filters"] is True


def test_office_filter_is_sent_to_repository():
    with (
        patch(
            "app.workspace.services.opportunity_list_service."
            "ProjectRepository.list_project_overviews",
            return_value=[],
        ) as list_overviews,
        patch(
            "app.workspace.services.opportunity_list_service."
            "ProjectRepository.list_sales_representatives",
            return_value=[],
        ),
    ):
        page = OpportunityListService.get_page({"office": "Cali"})

    list_overviews.assert_called_once_with({
        "status": "", "sales_rep": "", "customer_name": "",
        "origin": "", "office": "Cali",
    })
    assert page["filters"]["office"] == "Cali"


def test_commercial_office_mapping_uses_confirmed_cali_sellers():
    from app.workspace.constants.commercial_office import office_for_sales_rep

    assert office_for_sales_rep("  Diana Maria Velasquez C ") == "Cali"
    assert office_for_sales_rep("RICARDO LUGO") == "Cali"
    assert office_for_sales_rep("JEAN PIERRE FLOREZ") == "Bogotá"


def test_at_risk_filter_uses_central_health_calculation():
    records = [
        _record(id=1, has_overdue_followup=1),
        _record(id=2, last_activity_at=None),
    ]

    with (
        patch(
            "app.workspace.services.opportunity_list_service."
            "ProjectRepository.list_project_overviews",
            return_value=records,
        ),
        patch(
            "app.workspace.services.opportunity_list_service."
            "ProjectRepository.list_sales_representatives",
            return_value=["Ana"],
        ),
    ):
        page = OpportunityListService.get_page({"health": "at_risk"})

    assert [item["id"] for item in page["opportunities"]] == [1]


def test_origin_is_presented_with_user_facing_label():
    presented = OpportunityListService._present(
        _record(origin="visit")
    )

    assert presented["origin"] == "visit"
    assert presented["origin_label"] == "Visita"


def test_pipeline_summary_counts_and_values_each_open_stage():
    opportunities = [
        {"status": "prospect", "commercial_amount": None,
         "quote": None, "crm_potential_value": 1_500_000},
        {"status": "quoting", "commercial_amount": 2_000_000,
         "quote": None, "crm_potential_value": None},
        {"status": "won", "commercial_amount": 9_000_000,
         "quote": None, "crm_potential_value": None},
    ]

    summary = OpportunityListService._pipeline_summary(opportunities)

    assert [stage["count"] for stage in summary] == [1, 1, 0, 0]
    assert summary[0]["value_display"] == "COP 1.5 M"
    assert summary[1]["value_display"] == "COP 2.0 M"


def test_health_service_exposes_one_key_for_risk_conditions():
    overdue = ProjectHealthService.calculate(
        {
            "project": {"status": "negotiation"},
            "followups": [
                {"status": "pending", "due_date": "1900-01-01"}
            ],
            "activities": [],
        }
    )

    assert overdue["key"] == "at_risk"


def test_project_list_renders_selected_url_filters_and_empty_state():
    from app import __name__ as app_name
    from app.routes import register_blueprints
    from flask import Flask

    app = Flask(
        app_name,
        template_folder="../app/templates",
    )
    register_blueprints(app)

    page = {
        "opportunities": [],
        "filters": {
            "status": "negotiation",
            "sales_rep": "",
            "health": "at_risk",
            "customer_name": "Acme",
            "origin": "visit",
        },
        "has_active_filters": True,
        "filter_options": {
            "statuses": [
                {"value": "negotiation", "label": "Negociación"}
            ],
            "sales_representatives": [],
            "health": [{"value": "at_risk", "label": "En riesgo"}],
            "origins": [
                {"value": "manual", "label": "Manual"},
                {"value": "visit", "label": "Visita"},
            ],
        },
    }

    with patch(
        "app.routes.workspace.OpportunityListService.get_page",
        return_value=page,
    ) as get_page:
        response = app.test_client().get(
            "/workspace/projects"
            "?status=negotiation&health=at_risk&customer_name=Acme"
            "&origin=visit"
        )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'value="negotiation"' in html
    assert 'value="at_risk"' in html
    assert html.count("selected") == 3
    assert 'value="Acme"' in html
    assert 'name="origin"' in html
    assert 'value="visit"' in html
    assert "Pipeline de oportunidades" in html
    assert "Nueva oportunidad" in html
    assert "Creada desde" in html
    assert "Oportunidad" in html
    assert "No hay oportunidades que coincidan" in html
    get_page.assert_called_once()
