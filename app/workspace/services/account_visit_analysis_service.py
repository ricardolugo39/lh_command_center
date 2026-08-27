import hashlib
import json
from collections import Counter
from typing import Any

import requests

from app.configuration import resolve_settings
from app.database.transaction import connection_scope
from app.workspace.repositories.commercial_visit_repository import CommercialVisitRepository


class AccountVisitAnalysisService:
    PROMPT_VERSION = "visit-analysis-v1"

    @classmethod
    def state(cls, customer_id: int) -> dict[str, Any]:
        visits = CommercialVisitRepository.list_customer(customer_id)
        signature = cls._signature(visits)
        with connection_scope() as conn:
            row = conn.execute(
                "SELECT * FROM account_visit_analyses WHERE customer_id=? ORDER BY id DESC LIMIT 1",
                (customer_id,),
            ).fetchone()
        analysis = dict(row) if row else None
        if analysis:
            analysis["result"] = json.loads(analysis["analysis_json"])
        return {
            "analysis": analysis,
            "is_stale": bool(visits) and (not analysis or analysis["input_signature"] != signature),
            "has_visits": bool(visits),
            "visit_count": len(visits),
        }

    @classmethod
    def generate(cls, customer_id: int, *, actor: str = "system") -> dict[str, Any]:
        visits = CommercialVisitRepository.list_customer(customer_id)
        if not visits:
            raise ValueError("No hay visitas AppSheet para analizar.")
        signature = cls._signature(visits)
        with connection_scope() as conn:
            existing = conn.execute(
                "SELECT * FROM account_visit_analyses WHERE customer_id=? AND input_signature=? AND prompt_version=?",
                (customer_id, signature, cls.PROMPT_VERSION),
            ).fetchone()
        if existing:
            return cls.state(customer_id)
        deterministic = cls._deterministic(visits)
        result, model, status = deterministic, None, "deterministic"
        settings, _ = resolve_settings(("OPENAI_API_KEY", "OPENAI_MODEL"))
        if settings.get("OPENAI_API_KEY"):
            try:
                result = cls._openai(visits, deterministic, settings)
                model, status = settings.get("OPENAI_MODEL", "gpt-4.1-mini"), "completed"
            except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError):
                status = "fallback"
        with connection_scope() as conn:
            conn.execute(
                """INSERT INTO account_visit_analyses(customer_id,input_signature,
                source_visit_count,source_through_date,prompt_version,model,status,
                analysis_json,created_by) VALUES (?,?,?,?,?,?,?,?,?)""",
                (customer_id, signature, len(visits), max(v.get("visit_date") or "" for v in visits),
                 cls.PROMPT_VERSION, model, status, json.dumps(result, ensure_ascii=False), actor),
            )
        return cls.state(customer_id)

    @staticmethod
    def _signature(visits: list[dict[str, Any]]) -> str:
        values = [f"{v.get('source_visit_id')}:{v.get('source_row_hash')}" for v in visits]
        return hashlib.sha256("|".join(sorted(values)).encode()).hexdigest()

    @staticmethod
    def _deterministic(visits: list[dict[str, Any]]) -> dict[str, Any]:
        def values(field):
            return [str(v.get(field) or "").strip() for v in visits if str(v.get(field) or "").strip()]
        return {
            "executive_summary": f"Se analizaron {len(visits)} visitas comerciales.",
            "needs": values("detected_need")[:5],
            "risks": values("detected_risk")[:5],
            "competitors": [name for name, _ in Counter(values("competitor")).most_common(5)],
            "commitments": [{"visit_id": v["id"], "date": v.get("commitment_date"), "action": v.get("required_action")} for v in visits if v.get("requires_action")][:8],
            "opportunities": values("detected_need")[:5],
        }

    @staticmethod
    def _openai(visits, deterministic, settings):
        evidence = [{k: v.get(k) for k in ("id","visit_date","visit_type","visit_reason","executive_summary","detected_need","detected_risk","competitor","required_action","commitment_date")} for v in visits[:50]]
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings['OPENAI_API_KEY']}", "Content-Type": "application/json"},
            json={"model": settings.get("OPENAI_MODEL", "gpt-4.1-mini"), "temperature": 0.1,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": "Analiza visitas comerciales en español. Usa solo evidencia. Devuelve JSON con executive_summary, needs, risks, competitors, commitments y opportunities. Cada afirmación debe referenciar visit_id cuando corresponda."},
                               {"role": "user", "content": json.dumps({"deterministic": deterministic, "visits": evidence}, ensure_ascii=False)}]},
            timeout=60,
        )
        response.raise_for_status()
        return json.loads(response.json()["choices"][0]["message"]["content"])
