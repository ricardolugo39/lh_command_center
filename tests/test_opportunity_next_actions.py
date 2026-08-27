from datetime import date

from app.workspace.services.opportunity_next_action_service import (
    NextAction,
    OpportunityNextActionService,
)
from app.workspace.timeline.entry import (
    TimelineCategory,
    TimelineEntry,
    TimelineEventType,
)


TODAY = date(2026, 7, 22)


def _opportunity(**overrides):
    return {
        "id": 42,
        "status": "prospect",
        "current_blocker": None,
        "commercial_amount": "1000",
        **overrides,
    }


def _event(event_date="2026-07-22", category=TimelineCategory.COMMERCIAL):
    return TimelineEntry(
        id="activity-1",
        event_type=TimelineEventType.ACTIVITY,
        icon="calendar-check",
        color="neutral",
        title="Llamada",
        description="",
        source="Actividad",
        reference_id=1,
        date=event_date,
        user="Ana",
        endpoint="workspace.project_detail",
        category=category,
    )


def _actions(opportunity=None, **overrides):
    arguments = {
        "opportunity": opportunity or _opportunity(),
        "followups": [{"status": "pending"}],
        "pending_approval_count": 0,
        "timeline": [_event()],
        "quotes": [{"id": 1}],
        "today": TODAY,
    }
    arguments.update(overrides)
    return OpportunityNextActionService.get_actions(**arguments)


def test_waiting_customer_without_followup_recommends_scheduling():
    actions = _actions(
        _opportunity(status="waiting_customer"),
        followups=[],
    )

    assert [action.action_type for action in actions] == ["schedule_followup"]
    assert actions[0].priority == "High"


def test_pending_approval_recommends_review():
    actions = _actions(pending_approval_count=2)

    assert [action.action_type for action in actions] == [
        "review_pending_approvals"
    ]


def test_blocker_is_a_critical_action():
    actions = _actions(_opportunity(current_blocker="Validación técnica"))

    assert actions[0].action_type == "resolve_blocker"
    assert actions[0].priority == "Critical"


def test_activity_older_than_fifteen_days_recommends_contact():
    actions = _actions(timeline=[_event("2026-07-06")])

    assert [action.action_type for action in actions] == ["contact_customer"]


def test_exactly_fifteen_days_does_not_recommend_contact():
    assert _actions(timeline=[_event("2026-07-07")]) == ()


def test_quotation_stage_without_quote_recommends_creation():
    actions = _actions(_opportunity(status="quoting"), quotes=[])

    assert [action.action_type for action in actions] == ["create_quote"]


def test_missing_approved_commercial_value_recommends_completion():
    actions = _actions(_opportunity(commercial_amount=None))

    assert [action.action_type for action in actions] == [
        "complete_commercial_value"
    ]
    assert actions[0].priority == "Medium"


def test_combined_actions_are_unique_and_sorted_by_priority():
    actions = _actions(
        _opportunity(
            status="waiting_customer",
            current_blocker="Esperando ficha",
            commercial_amount=None,
        ),
        followups=[],
        pending_approval_count=1,
        timeline=[_event("2026-06-01")],
        quotes=[],
    )

    assert [action.priority for action in actions] == [
        "Critical", "High", "High", "High", "High", "Medium",
    ]
    action_types = [action.action_type for action in actions]
    assert len(action_types) == len(set(action_types)) == 6


def test_every_action_has_a_working_navigation_target():
    actions = _actions(
        _opportunity(
            status="waiting_customer",
            current_blocker="Esperando ficha",
            commercial_amount=None,
        ),
        followups=[],
        pending_approval_count=1,
        timeline=[_event("2026-06-01")],
        quotes=[],
    )
    expected = {
        "schedule_followup": "workspace.project_detail",
        "review_pending_approvals": "workspace.commercial_approval_list",
        "resolve_blocker": "workspace.project_detail",
        "contact_customer": "workspace.project_detail",
        "create_quote": "workspace.edit_project",
        "complete_commercial_value": "workspace.commercial_approval_new",
    }

    assert all(isinstance(action, NextAction) for action in actions)
    assert {
        action.action_type: action.navigation["endpoint"] for action in actions
    } == expected
    assert all(
        action.navigation["values"]["project_id"] == 42
        for action in actions
    )


def test_closed_opportunity_has_no_actionable_recommendations():
    actions = _actions(
        _opportunity(
            status="won",
            current_blocker="Dato histórico",
            commercial_amount=None,
        ),
        followups=[],
        pending_approval_count=1,
        timeline=[_event("2026-01-01")],
        quotes=[],
    )

    assert actions == ()
