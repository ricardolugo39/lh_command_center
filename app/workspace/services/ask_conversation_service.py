from typing import Any, Iterable

from werkzeug.datastructures import FileStorage

from app.database.transaction import transaction
from app.workspace.repositories.ask_repository import AskRepository
from app.workspace.services.ask_execution_service import AskExecutionService
from app.workspace.services.ask_file_service import AskFileService
from app.workspace.services.ask_openai_service import AskOpenAIError
from app.workspace.services.ask_preparation_service import AskPreparationService


class AskConversationService:
    """Turns a message and optional files into the next investigation turn."""

    @classmethod
    def start(
        cls, goal: str, uploads: Iterable[FileStorage], user_id: int,
        customer_id: int | None = None,
    ) -> int:
        analysis_id = AskPreparationService.create(goal, user_id)
        if customer_id:
            AskPreparationService.select_customer(analysis_id, customer_id)
        cls._upload(analysis_id, uploads)
        cls._advance(analysis_id)
        return analysis_id

    @classmethod
    def respond(
        cls, analysis_id: int, user_id: int, message: str,
        uploads: Iterable[FileStorage], customer_id: int | None = None,
    ) -> int:
        content = str(message or "").strip()
        selected_uploads = [
            upload for upload in uploads if upload and upload.filename
        ]
        if not content and not selected_uploads:
            raise ValueError("Escriba un mensaje o adjunte un archivo.")
        if content:
            target_id = AskPreparationService.continue_investigation(
                analysis_id, user_id, content
            )
        else:
            target_id = AskPreparationService.evidence_target(
                analysis_id, user_id
            )
        if customer_id:
            AskPreparationService.select_customer(target_id, customer_id)
        cls._upload(target_id, selected_uploads)
        if selected_uploads:
            with transaction():
                AskRepository.add_message(target_id, {
                    "role": "analyst",
                    "content": cls._upload_message(selected_uploads),
                    "clarification_type": "evidence_received",
                })
        cls._advance(target_id)
        return target_id

    @classmethod
    def ensure_progress(cls, analysis_id: int) -> None:
        analysis = AskRepository.get(analysis_id)
        if analysis and analysis["status"] in {"draft", "ready"}:
            cls._advance(analysis_id)

    @classmethod
    def _advance(cls, analysis_id: int) -> None:
        page = AskPreparationService.refresh(analysis_id)
        analysis = page["analysis"]
        if analysis["blocking_reasons"]:
            cls._say(analysis_id, cls._clarification_message(
                analysis["blocking_reasons"]
            ))
            return
        cls._say(
            analysis_id,
            "Entendido. Estoy revisando la evidencia disponible y consultando "
            "las fuentes necesarias. Comenzaré la investigación ahora.",
            "investigation_started",
        )
        try:
            completed = AskExecutionService.execute(analysis_id)
        except (AskOpenAIError, ValueError, RuntimeError) as error:
            cls._say(
                analysis_id,
                "No pude completar este turno. Conservé la evidencia y el "
                f"conocimiento recuperado. Detalle: {error}",
                "investigation_issue",
            )
            return
        artifacts = AskRepository.list_artifacts(analysis_id)
        if artifacts:
            titles = ", ".join(artifact["title"] for artifact in artifacts)
            cls._say(
                analysis_id,
                f"Listo. Preparé: {titles}. Puede revisarlos debajo de esta "
                "conversación o pedirme otro formato.",
                "artifacts_ready",
            )
            return
        knowledge = completed.get("evidence") or {}
        summary = knowledge.get("summary") or {}
        cls._say(
            analysis_id,
            "La investigación está completa. Encontré "
            f"{summary.get('findings', 0)} hallazgo(s), "
            f"{summary.get('risks', 0)} riesgo(s), "
            f"{summary.get('opportunities', 0)} oportunidad(es) y "
            f"{summary.get('pending_investigations', 0)} asunto(s) que "
            "todavía requieren evidencia. ¿Qué le gustaría hacer ahora? "
            "Puede pedirme una matriz de decisiones, un reporte ejecutivo, "
            "un Excel, preparar una reunión o investigar otra hipótesis.",
            "knowledge_ready",
        )

    @staticmethod
    def _upload(analysis_id: int, uploads: Iterable[FileStorage]) -> None:
        for upload in uploads:
            if upload and upload.filename:
                AskFileService.upload(analysis_id, upload)

    @staticmethod
    def _upload_message(uploads: list[FileStorage]) -> str:
        names = ", ".join(upload.filename or "archivo" for upload in uploads)
        return (
            f"He incorporado la nueva evidencia: {names}. Actualizaré los "
            "hallazgos con esta información."
        )

    @staticmethod
    def _clarification_message(reasons: list[str]) -> str:
        questions = " ".join(str(reason) for reason in reasons)
        return (
            "Necesito confirmar un punto que no pude resolver con la evidencia "
            f"disponible: {questions} Responda en esta conversación."
        )

    @staticmethod
    def _say(
        analysis_id: int, content: str,
        clarification_type: str = "clarification",
    ) -> None:
        with transaction():
            messages = AskRepository.list_messages(analysis_id)
            if messages and messages[-1]["role"] == "analyst" and (
                messages[-1]["content"] == content
            ):
                return
            AskRepository.add_message(analysis_id, {
                "role": "analyst", "content": content,
                "clarification_type": clarification_type,
            })
