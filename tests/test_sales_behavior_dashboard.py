from app.workspace.services.strategic_account_service import StrategicAccountService
from datetime import date


def _row(month, number, value, product="6204SKF", family="RODAMIENTOS"):
    return {
        "sale_date": f"2026-{month:02d}-10", "prefijo": "FV", "numero": number,
        "product_id": product, "family_name": family, "neto": value,
    }


def test_behavior_detects_recurring_customer_with_project_spike():
    rows = [_row(month, month, 100) for month in range(1, 13)]
    rows.append(_row(6, 99, 2000, "12B-TREN", "TRANSMISION DE POTENCIA"))

    result = StrategicAccountService._purchase_behavior(rows)

    assert result["label"] == "Recurrente con picos de proyecto"
    assert result["anomalies"][0]["month"] == "2026-06"
    assert result["type_mix"][0]["name"] == "Transmisión de potencia"
    assert result["brand_mix"][0]["name"] == "TREN"


def test_brand_and_type_classification_remain_explicit_fallbacks():
    result = StrategicAccountService._purchase_behavior([
        _row(1, 1, 50, "UNKNOWN", "OTRA FAMILIA")
    ])

    assert result["brand_mix"][0]["name"] == "Otros"
    assert result["type_mix"][0]["name"] == "Otros"


def test_sales_diagnosis_explains_smaller_tickets_and_product_churn():
    rows = [
        {**_row(1, 1, 100, "6204SKF"), "sale_date": "2025-01-10"},
        {**_row(2, 2, 900, "PROJECTSKF"), "sale_date": "2025-02-10"},
        {**_row(1, 3, 80, "6204SKF"), "sale_date": "2026-01-10"},
        {**_row(2, 4, 50, "NEWINA"), "sale_date": "2026-02-10"},
    ]

    result = StrategicAccountService._sales_diagnosis(
        rows,
        visits=[{
            "id": 8, "visit_date": "2026-02-15", "requires_action": 1,
            "required_action": "Revisar referencias", "commitment_date": "2026-03-01",
            "visit_status": "Abierto", "visit_reason": "Proyecto de monitoreo",
        }],
        opportunities=[{"amount": 500}],
        as_of=date(2026, 8, 10),
    )

    assert result["documents"] == {"current": 2, "previous": 2}
    assert result["delta"] == -870
    assert result["components"][0]["count"] == 1
    assert result["components"][0]["value"] == -900
    assert result["components"][1]["value"] == 50
    assert "tickets más pequeños" in result["headline"]
    assert result["visit_reading"]["pending"][0]["overdue"] is True
    assert result["pipeline"]["count"] == 1

