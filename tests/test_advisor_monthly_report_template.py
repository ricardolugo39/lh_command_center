from pathlib import Path

from jinja2 import DictLoader, Environment


def test_advisor_monthly_report_renders_visit_items():
    source = Path("app/templates/team/advisor_monthly_report.html").read_text()
    environment = Environment(loader=DictLoader({
        "report.html": source,
        "base.html": "{% block content %}{% endblock %}",
    }))
    environment.globals["url_for"] = lambda endpoint, **values: (
        f"/{endpoint}/{values}"
    )
    page = {
        "advisor": "JAIRO DAVID VERA", "office": "Cali",
        "month": "2026-08", "month_label": "Agosto 2026",
        "period_start": "2026-08-01", "period_end": "2026-08-31",
        "generated_on": "2026-09-01", "transition_note": None,
        "sales": {
            "display_current": "COP 1", "display_previous": "COP 2",
            "display_previous_month": "COP 3", "display_ytd": "COP 1",
            "delta": -1, "change": -50, "ytd_change": -50,
            "customers": [], "brands": [], "products": [],
            "customer_movements": {
                "lost_previous_month": [], "lost_previous_year": [],
                "declining": [], "new_or_recovered": [],
            },
        },
        "visits": {
            "total": 1, "customers": 1, "with_action": 0,
            "items": [{
                "id": 1, "customer_name": "Cliente", "source_customer_name": "",
                "visit_reason": "Seguimiento", "executive_summary": "",
                "visit_date": "2026-08-10",
            }],
        },
        "opportunities": {
            "won_count": 0, "lost_count": 0, "won_value_display": "COP 0",
            "lost_value_display": "COP 0", "escalated_losses": 0,
            "documented_losses": 0, "lost": [],
        },
        "pipeline": {"pipeline": [], "opportunities": []},
        "signals": [],
    }
    rendered = environment.get_template("report.html").render(page=page)
    assert "Seguimiento" in rendered
    assert "JAIRO DAVID VERA" in rendered
