from flask import render_template

from app.database.transaction import transactional
from app.workspace.repositories.ask_repository import AskRepository
from app.workspace.services.ask_analysis_engine import AskAnalysisEngine


class AskReportService:
    @classmethod
    @transactional
    def render_and_store(cls, analysis_id: int) -> str:
        analysis = AskRepository.get(analysis_id)
        if not analysis or analysis["status"] != "completed":
            raise ValueError("El reporte todavía no está disponible.")
        artifacts = AskRepository.list_artifacts(analysis_id)
        if not artifacts:
            artifacts = AskAnalysisEngine.build_artifacts(
                analysis.get("evidence") or {},
                analysis.get("ai_response") or {},
            )
            AskRepository.replace_artifacts(analysis_id, artifacts)
        markup = render_template(
            "ask/report.html", analysis=analysis, artifacts=artifacts,
        )
        AskRepository.update(analysis_id, {"report_html": markup})
        return markup

    @classmethod
    @transactional
    def mark_reviewed(cls, analysis_id: int) -> None:
        analysis = AskRepository.get(analysis_id)
        if not analysis or analysis["status"] != "completed":
            raise ValueError("El análisis todavía no está disponible.")
        AskRepository.update(
            analysis_id, {"lifecycle_status": "reviewed"}
        )

    @classmethod
    @transactional
    def mark_exported(cls, analysis_id: int) -> None:
        analysis = AskRepository.get(analysis_id)
        if not analysis or analysis["status"] != "completed":
            raise ValueError("El análisis todavía no está disponible.")
        AskRepository.update(
            analysis_id, {"lifecycle_status": "exported"}
        )
