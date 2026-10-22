from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask
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
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.get_file",
        lambda initiative_id: None,
    )
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.list_files",
        lambda: [],
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


def test_warehouse_distribution_is_balanced_and_preserves_existing(monkeypatch):
    source = [
        {
            "customer_id": str(index), "name": f"Cliente {index}",
            "city": "BOGOTA", "advisor": "ALMACEN", "other_sales": index,
        }
        for index in range(1, 13)
    ]
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.LinearMotionRepository.segment_opportunity",
        lambda segment, brand: {"customers": source},
    )
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.list_customers",
        lambda initiative_id: [{"customer_erp_id": "1", "advisor": "HAROL CAMARGO"}],
    )
    saved = []
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.upsert_customer",
        lambda initiative_id, customer: saved.append(customer),
    )
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeRepository.create_event",
        lambda **values: 1,
    )

    result = InitiativeCampaignService.distribute_warehouse_customers.__wrapped__(10)

    counts = [item["assigned"] for item in result["assignments"]]
    assert result["total"] == 12
    assert len(saved) == 11
    assert max(counts) - min(counts) <= 1


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


def test_hourly_sync_continues_when_one_campaign_fails(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.list_files",
        lambda: [
            {"initiative_id": 10, "advisor": "ANA"},
            {"initiative_id": 11, "advisor": "BEA"},
        ],
    )
    synced = []

    def sync(initiative_id, advisor=None):
        if initiative_id == 10:
            raise RuntimeError("Microsoft no disponible")
        synced.append(initiative_id)
        return {"updated": 1, "ignored": 0}

    failures = []
    monkeypatch.setattr(
        InitiativeCampaignService, "sync_from_onedrive", staticmethod(sync),
    )
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.mark_sync",
        lambda initiative_id, **values: failures.append((initiative_id, values)),
    )
    app.config["EMAIL_PROVIDER"] = "microsoft"

    with app.app_context():
        result = InitiativeCampaignService.sync_all_from_onedrive()

    assert result == {"processed": 2, "succeeded": 1, "failed": 1}
    assert synced == [11]
    assert failures == [(10, {
        "advisor": "ANA",
        "etag": None,
        "status": "error",
        "message": "Microsoft no disponible",
    })]


def test_followup_automation_sends_two_reminders_then_escalates(monkeypatch):
    app = Flask(__name__)
    app.config.update(EMAIL_PROVIDER="microsoft", MICROSOFT_MAILBOX_ADDRESS="ventas@example.com")
    sent = []
    app.extensions["email_provider"] = type("Provider", (), {
        "send": lambda self, **message: sent.append(message),
    })()
    record = {
        "id": 4, "initiative_id": 10, "advisor": "ANA PEREZ",
        "recipient": "ana@example.com", "web_url": "https://excel.example/file",
        "sent_at": "2026-10-01 08:00:00", "first_reminder_at": None,
        "second_reminder_at": None, "escalated_at": None,
    }
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.list_files",
        lambda: [record],
    )
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.advisor_has_progress",
        lambda *args: False,
    )
    changes = []
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.mark_automation",
        lambda file_id, **values: changes.append(values),
    )
    events = []
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeRepository.create_event",
        lambda **values: events.append(values),
    )
    tz = ZoneInfo("America/Bogota")
    with app.app_context():
        assert InitiativeCampaignService.run_followup_automation(
            datetime(2026, 10, 6, 8, 0, tzinfo=tz)
        ) == {"reminders": 1, "escalations": 0}
        record["first_reminder_at"] = "2026-10-06 08:00:00"
        assert InitiativeCampaignService.run_followup_automation(
            datetime(2026, 10, 12, 8, 0, tzinfo=tz)
        ) == {"reminders": 1, "escalations": 0}
        record["second_reminder_at"] = "2026-10-12 08:00:00"
        assert InitiativeCampaignService.run_followup_automation(
            datetime(2026, 10, 14, 8, 0, tzinfo=tz)
        ) == {"reminders": 0, "escalations": 1}

    assert len(sent) == 2
    assert sent[1]["subject"].startswith("Recordatorio 2 de 2")
    assert changes[-1]["escalated"] is True
    assert events[-1]["event_type"] == "campaign_escalation"


def test_followup_automation_stops_when_advisor_has_progress(monkeypatch):
    app = Flask(__name__)
    app.config["EMAIL_PROVIDER"] = "microsoft"
    app.extensions["email_provider"] = object()
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.list_files",
        lambda: [{"sent_at": "2026-10-01 08:00:00", "recipient": "ana@example.com",
                  "initiative_id": 10, "advisor": "ANA"}],
    )
    monkeypatch.setattr(
        "app.workspace.services.initiative_campaign_service.InitiativeCampaignRepository.advisor_has_progress",
        lambda *args: True,
    )
    with app.app_context():
        result = InitiativeCampaignService.run_followup_automation(
            datetime(2026, 10, 15, 8, 0, tzinfo=ZoneInfo("America/Bogota"))
        )
    assert result == {"reminders": 0, "escalations": 0}
