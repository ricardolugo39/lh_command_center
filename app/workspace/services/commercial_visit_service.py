from collections import Counter
from datetime import date
from typing import Any

from app.database.transaction import transactional
from app.workspace.connectors.visit_source import GoogleSheetsVisitSource, VisitSourceAdapter
from app.workspace.repositories.commercial_visit_repository import CommercialVisitRepository
from app.workspace.repositories.customer_repository import CustomerRepository
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.services.visit_attachment_resolver import VisitAttachmentResolver
from app.workspace.services.visit_normalizer import VisitNormalizer
from app.workspace.services.opportunity_timeline_service import OpportunityTimelineService


class CommercialVisitService:
    SOURCE_SYSTEM = "appsheet_google_sheets"

    @classmethod
    def sync_configured_source(cls):
        return cls.sync(GoogleSheetsVisitSource.from_environment())

    @classmethod
    def rebuild_configured_source(cls):
        source=GoogleSheetsVisitSource.from_environment()
        rows=source.read_rows()
        return cls._rebuild_rows(rows)

    @classmethod
    def sync(cls, source: VisitSourceAdapter):
        rows = source.read_rows()
        return cls._import_rows(rows)

    @classmethod
    @transactional
    def _rebuild_rows(cls, rows: list[dict]):
        links=CommercialVisitRepository.list_source_project_links(
            cls.SOURCE_SYSTEM)
        removed=CommercialVisitRepository.delete_source(cls.SOURCE_SYSTEM)
        summary=cls._import_rows(rows)
        for source_visit_id,project_id in links.items():
            visit=CommercialVisitRepository.get_by_source(
                cls.SOURCE_SYSTEM,source_visit_id)
            if visit:
                cls.link_to_project(visit["id"],project_id)
        summary["removed"]=removed
        return summary

    @classmethod
    @transactional
    def _import_rows(cls, rows: list[dict]):
        run_id = CommercialVisitRepository.create_sync_run(cls.SOURCE_SYSTEM)
        summary = {"rows_read":len(rows),"inserted":0,"updated":0,"unchanged":0,
                   "unmatched":0,"possible_duplicates":0,"errors":0,
                   "error_details":[]}
        customers = cls._customer_index()
        for index,row in enumerate(rows,start=2):
            try:
                values = VisitNormalizer.normalize(row)
            except ValueError as exc:
                summary["errors"] += 1
                summary["error_details"].append({"row":index,"error":str(exc)})
                continue
            values.update(cls._match_customer(values["customer_erp_id"],customers))
            values["possible_duplicate"] = int(
                CommercialVisitRepository.find_possible_duplicate(
                    values,values["source_visit_id"]))
            existing = CommercialVisitRepository.get_by_source(
                cls.SOURCE_SYSTEM,values["source_visit_id"])
            if existing:
                values["project_id"] = existing.get("project_id")
            match_changed = bool(existing and (
                existing.get("customer_id") != values.get("customer_id") or
                existing.get("customer_match_status") != values.get("customer_match_status")
            ))
            if (existing and existing["source_row_hash"] == values["source_row_hash"]
                    and not match_changed):
                summary["unchanged"] += 1
                if existing["customer_match_status"] != "matched": summary["unmatched"] += 1
                if existing["possible_duplicate"]: summary["possible_duplicates"] += 1
                continue
            if existing:
                CommercialVisitRepository.update(existing["id"],values)
                visit_id=existing["id"]; summary["updated"] += 1
            else:
                values["project_id"] = None
                visit_id=CommercialVisitRepository.insert(cls.SOURCE_SYSTEM,values)
                summary["inserted"] += 1
            if values["customer_match_status"] != "matched": summary["unmatched"] += 1
            if values["possible_duplicate"]: summary["possible_duplicates"] += 1
            if values["requires_action"]:
                CommercialVisitRepository.upsert_followup(
                    visit_id,values["source_visit_id"],values)
            else:
                CommercialVisitRepository.close_source_followup(
                    values["source_visit_id"]
                )
            if values.get("project_id"):
                cls._publish_project_event(visit_id,values["project_id"],values)
        CommercialVisitRepository.finish_sync_run(run_id,summary)
        summary["run_id"]=run_id
        return summary

    @classmethod
    def _customer_index(cls):
        index={}
        for customer in CustomerRepository.list_customers():
            key=VisitNormalizer.normalize_identifier(customer.get("erp_customer_id"))
            if key:index.setdefault(key,[]).append(customer["id"])
        return index

    @classmethod
    def _match_customer(cls,key,index):
        candidates=index.get(key,[]) if key else []
        if len(candidates)==1:return {"customer_id":candidates[0],"customer_match_status":"matched"}
        if len(candidates)>1:return {"customer_id":None,"customer_match_status":"ambiguous"}
        manual=CommercialVisitRepository.get_manual_match(key) if key else None
        return {"customer_id":manual,"customer_match_status":"matched" if manual else "unmatched"}

    @classmethod
    @transactional
    def link_to_project(cls, visit_id: int, project_id: int):
        project=ProjectRepository.get_project(project_id)
        if not project:raise ValueError("La oportunidad no existe.")
        visits=[visit for visit in CommercialVisitRepository.list_customer(project["customer_id"])
                if visit["id"]==visit_id]
        if not visits:raise ValueError("La visita no pertenece al cliente de la oportunidad.")
        CommercialVisitRepository.link_project(visit_id,project_id)
        cls._publish_project_event(visit_id,project_id,visits[0])

    @classmethod
    def _publish_project_event(cls,visit_id,project_id,visit):
        if CommercialVisitRepository.has_project_event(project_id,visit_id):return
        OpportunityTimelineService.publish_visit_event(
            visit_id=visit_id,project_id=project_id,visit=visit)

    @classmethod
    def get_customer_page(cls,customer_id:int,activity_filter="all"):
        customer=CustomerRepository.get_customer(customer_id)
        if not customer:raise ValueError("El cliente no existe.")
        visits=[cls._present(visit) for visit in CommercialVisitRepository.list_customer(customer_id)]
        filtered = visits if activity_filter in {"all", "visits"} else []
        types=Counter(visit["visit_type"] for visit in visits)
        return {"customer":customer,"visits":filtered,"filter":activity_filter,
                "metrics":{"total":len(visits),"last_visit":visits[0]["visit_date"] if visits else None,
                           "by_type":dict(types),"pending_actions":sum(v["requires_action"] and v["visit_status"]!="Cerrado" for v in visits),
                           "advisors":len({v["advisor_name"] for v in visits if v["advisor_name"]})}}

    @classmethod
    def get_visit(cls,visit_id:int):
        visit=CommercialVisitRepository.get(visit_id)
        if not visit:raise ValueError("La visita no existe.")
        return cls._present(visit)

    @classmethod
    def get_quality_page(cls):
        rows=[cls._present(row) for row in CommercialVisitRepository.list_quality_issues()]
        return {"visits":rows,"latest_sync":CommercialVisitRepository.latest_sync_run(),
                "counts":{"unmatched":sum(v["customer_match_status"]=="unmatched" for v in rows),
                          "ambiguous":sum(v["customer_match_status"]=="ambiguous" for v in rows),
                          "duplicates":sum(v["possible_duplicate"] for v in rows),
                          "attachments":sum(v["attachment_reference"] is not None for v in rows)}}

    @staticmethod
    def get_integration_status():
        import json

        configuration = GoogleSheetsVisitSource.configuration_status()
        latest = CommercialVisitRepository.latest_sync_run()
        if latest:
            try:
                latest["errors"] = json.loads(
                    latest.get("error_summary") or "[]"
                )
            except (TypeError, ValueError):
                latest["errors"] = []
        return {
            **configuration,
            "worksheet": configuration["worksheet_name"] or "Sin configurar",
            "latest_sync": latest,
            "metrics": CommercialVisitRepository.integration_metrics(),
        }

    @staticmethod
    def _present(visit):
        warnings=[]
        try:
            import json; warnings=json.loads(visit.get("quality_warnings") or "[]")
        except (ValueError,TypeError):pass
        future=bool(visit.get("visit_date") and visit["visit_date"]>date.today().isoformat())
        return {**visit,"quality_warnings":warnings,"is_scheduled":future,
                "attachment":VisitAttachmentResolver.resolve(visit.get("attachment_reference")),
                "is_opportunity_candidate":bool(visit.get("generate_opportunity_requested"))}
