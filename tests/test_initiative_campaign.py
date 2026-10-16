from io import BytesIO

from openpyxl import load_workbook

from app.workspace.services.initiative_campaign_service import (
    InitiativeCampaignService,
)


CUSTOMERS = [
    {
        "customer_erp_id": "860034812",
        "customer_name": "PELEX S.A.S - PELICULAS EXTRUIDAS",
        "city": "BOGOTA D.C.",
        "advisor": "JOHN FREDY MORENO",
        "priority": "Alta",
        "brands": "FAG,SKF,NTN,INA,HIW",
        "competitor_linear_brands": "HIW,INA",
        "last_purchase": "2026-09-21",
        "other_sales": 62142038,
        "status": "Pendiente",
        "source_key": "THK-PLASTICOS-860034812",
    }
]


def test_campaign_summary_uses_percentages(monkeypatch):
    customer = {**CUSTOMERS[0], "status": "Contactado", "application": "Extrusora", "opportunity_decision": "Sí"}
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.list_customers",
        lambda initiative_id: [customer],
    )

    campaign = InitiativeCampaignService.get_campaign(10)

    assert campaign["summary"] == {
        "assigned": 1,
        "contacted": 1,
        "contacted_pct": 100,
        "applications": 1,
        "applications_pct": 100,
        "opportunities": 1,
        "opportunities_pct": 100,
    }


def test_campaign_workbook_round_trip(monkeypatch):
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeRepository.get_initiative",
        lambda initiative_id: {"id": initiative_id, "name": "Homologación THK - Plásticos"},
    )
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.list_customers",
        lambda initiative_id: CUSTOMERS,
    )
    updates = []
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.update_tracking",
        lambda initiative_id, source_key, values: updates.append((source_key, values)) or True,
    )
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeRepository.create_event",
        lambda **kwargs: 1,
    )

    stream, filename = InitiativeCampaignService.export_workbook(10)
    workbook = load_workbook(stream)
    sheet = workbook["Seguimiento"]
    sheet["E4"] = "Contactado"
    sheet["H4"] = "Extrusora"
    sheet["M4"] = "Sí"
    edited = BytesIO()
    workbook.save(edited)
    edited.seek(0)

    result = InitiativeCampaignService.import_workbook.__wrapped__(10, edited)

    assert filename.endswith("John_Fredy_Moreno.xlsx")
    assert result == {"updated": 1, "ignored": 0}
    assert updates[0][0] == "THK-PLASTICOS-860034812"
    assert updates[0][1]["application"] == "Extrusora"
    assert updates[0][1]["opportunity_decision"] == "Sí"
