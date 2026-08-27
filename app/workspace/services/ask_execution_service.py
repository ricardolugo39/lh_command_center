from datetime import datetime, timezone
from typing import Any

from app.database.transaction import transaction
from app.workspace.repositories.ask_repository import AskRepository
from app.workspace.services.ask_analysis_engine import AskAnalysisEngine
from app.workspace.services.ask_openai_service import (
    AskOpenAIError, AskOpenAIService,
)


class AskExecutionService:
    @classmethod
    def execute(cls, analysis_id: int) -> dict[str, Any]:
        analysis = AskRepository.get(analysis_id)
        if not analysis:
            raise ValueError("El análisis no existe.")
        if analysis["status"] not in {"ready", "failed"}:
            raise ValueError("El análisis todavía no está listo.")
        with transaction():
            AskRepository.update(analysis_id, {
                "status": "running", "lifecycle_status": "running",
                "error_message": None,
            })
        try:
            files = AskRepository.list_files(analysis_id)
            plan = analysis.get("plan") or {}
            if (
                isinstance(plan, dict)
                and plan.get("mode") == "deliverable"
                and analysis.get("evidence")
            ):
                knowledge = analysis["evidence"]
                ai_response = AskOpenAIService.specify_artifacts(
                    knowledge, analysis.get("focus") or analysis["objective"]
                )
                new_artifacts = AskAnalysisEngine.build_artifacts(
                    knowledge, ai_response
                )
                existing = AskRepository.list_artifacts(analysis_id)
                existing_keys = {artifact["key"] for artifact in existing}
                for artifact in new_artifacts:
                    base = artifact["key"]
                    suffix = 2
                    while artifact["key"] in existing_keys:
                        artifact["key"] = f"{base}-{suffix}"
                        suffix += 1
                    existing_keys.add(artifact["key"])
                artifacts = [*existing, *new_artifacts]
            else:
                knowledge = AskAnalysisEngine.execute(analysis, files)
                with transaction():
                    AskRepository.update(analysis_id, {
                        "evidence": knowledge,
                    })
                ai_response = AskOpenAIService.generate(knowledge)
                knowledge["analyst_synthesis"] = ai_response
                artifacts = []
            with transaction():
                AskRepository.update(analysis_id, {"evidence": knowledge})
                AskRepository.replace_artifacts(analysis_id, artifacts)
                AskRepository.update(analysis_id, {
                    "status": "completed", "ai_response": ai_response,
                    "lifecycle_status": "ready_review",
                    "executed_at": datetime.now(timezone.utc).isoformat(),
                    "error_message": None,
                })
        except Exception as error:
            with transaction():
                AskRepository.update(analysis_id, {
                    "status": "failed", "lifecycle_status": "failed",
                    "error_message": str(error),
                })
            if isinstance(error, (ValueError, AskOpenAIError)):
                raise
            raise RuntimeError("No fue posible ejecutar el análisis.") from error
        return AskRepository.get(analysis_id) or {}
