import hashlib
import json
from typing import Any

from app.workspace.services.ask_openai_service import AskOpenAIService


class AskInvestigationPlanner:
    """Plans an investigation without assuming a business domain."""

    @classmethod
    def build(
        cls,
        analysis: dict[str, Any],
        files: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        instruction = str(analysis.get("focus") or "")
        has_knowledge = bool(analysis.get("evidence"))
        # Once knowledge exists, the next instruction is interpreted against
        # that knowledge. The artifact planner may return any output contract;
        # no domain-specific intent list is needed here.
        deliverable_requested = has_knowledge and bool(instruction.strip())
        available = [
            {
                "source": file["original_filename"],
                "kind": file.get("inspection", {}).get("kind", "unknown"),
                "status": file["processing_status"],
            }
            for file in files
        ]
        if context.get("customer"):
            available.append({
                "source": "Commercial Command Center",
                "kind": "customer_context",
                "status": "available",
            })
        capabilities = ["uploaded_evidence"] if files else []
        if context.get("customer"):
            capabilities.append("customer_context")
        questions = []
        if not str(analysis.get("objective") or "").strip():
            questions.append("¿Qué decisión debe apoyar esta investigación?")
        failed = [
            item["source"] for item in available
            if item["status"] == "failed"
        ]
        planning_context = {
            "goal": analysis["objective"],
            "current_instruction": instruction or None,
            "resolved_context": {
                "customer": (
                    context.get("customer", {}).get("name")
                    if context.get("customer") else None
                ),
                "brands": context.get("brands", []),
            },
            "available_evidence": available,
            "available_capabilities": capabilities,
            "prior_knowledge_summary": (
                analysis.get("evidence", {}).get("summary", {})
                if has_knowledge else {}
            ),
        }
        signature = hashlib.sha256(json.dumps(
            planning_context, ensure_ascii=False, sort_keys=True,
            default=str,
        ).encode()).hexdigest()
        previous = analysis.get("plan")
        if (
            isinstance(previous, dict)
            and previous.get("_input_signature") == signature
        ):
            return previous
        dynamic = AskOpenAIService.plan_investigation(planning_context) or {}
        selected_capabilities = [
            name for name in dynamic.get("capabilities", capabilities)
            if name in capabilities
        ]
        fallback = {
            "mode": "deliverable" if deliverable_requested else "investigation",
            "goal": analysis["objective"],
            "expected_decision": (
                "Definida por el usuario durante la investigación"
            ),
            "required_information": [
                "Evidencia suficiente para responder el objetivo",
                "Origen y confiabilidad de cada hallazgo",
                "Límites que impidan una conclusión responsable",
            ],
            "available_evidence": available,
            "missing_evidence": [
                f"No fue posible procesar {name}." for name in failed
            ],
            "possible_calculations": cls._possible_calculations(files),
            "assumptions": [],
            "questions": questions,
            "inferred_without_question": [
                "La estructura de los archivos se utilizará tal como fue "
                "detectada localmente."
            ] if files else [],
            "capabilities": capabilities,
            "potential_outputs": [
                "Resumen de hallazgos", "Reporte ejecutivo",
                "Dataset de trabajo", "Tabla", "Excel", "HTML",
            ],
            "steps": cls._steps(capabilities, deliverable_requested),
        }
        for key in (
            "required_information", "missing_evidence",
            "possible_calculations", "assumptions", "questions",
            "inferred_without_question", "potential_outputs", "steps",
        ):
            if isinstance(dynamic.get(key), list):
                fallback[key] = [
                    str(item) for item in dynamic[key][:30]
                    if isinstance(item, (str, int, float))
                ]
        if isinstance(dynamic.get("expected_decision"), str):
            fallback["expected_decision"] = dynamic["expected_decision"]
        fallback["capabilities"] = selected_capabilities
        fallback["_input_signature"] = signature
        return fallback

    @staticmethod
    def _possible_calculations(files: list[dict[str, Any]]) -> list[str]:
        calculations = []
        if any(
            file.get("inspection", {}).get("kind") == "spreadsheet"
            for file in files
        ):
            calculations.extend([
                "Perfilar campos y calidad de datos",
                "Calcular métricas descriptivas aplicables",
                "Comparar tablas cuando compartan estructura",
            ])
        if files:
            calculations.append(
                "Contrastar hallazgos entre fuentes estructuradas"
            )
        return calculations

    @staticmethod
    def _steps(
        capabilities: list[str], deliverable_requested: bool
    ) -> list[str]:
        if deliverable_requested:
            return [
                "Interpretar el entregable solicitado.",
                "Seleccionar conocimiento y evidencia pertinente.",
                "Construir artefactos con estructura dinámica.",
                "Validar trazabilidad y guardar la nueva versión.",
            ]
        steps = [
            "Confirmar el objetivo y la decisión esperada.",
            "Inventariar la evidencia disponible y sus límites.",
        ]
        if capabilities:
            steps.append(
                "Ejecutar únicamente las capacidades requeridas por el plan."
            )
        steps.extend([
            "Consolidar hechos, métricas, hallazgos y asuntos pendientes.",
            "Presentar el conocimiento para continuar la conversación.",
        ])
        return steps
