from typing import Any

from app.workspace.services.ask_capabilities import AskCapabilityRegistry
from app.workspace.services.ask_investigation_planner import (
    AskInvestigationPlanner,
)


class AskAnalysisEngine:
    """Executes a plan and returns knowledge, never a predetermined report."""

    @staticmethod
    def initial_assumptions(objective: str) -> dict[str, Any]:
        return {}

    @staticmethod
    def preparation_requirements(
        analysis: dict[str, Any], files: list[dict[str, Any]],
        context: dict[str, Any], mappings: dict[str, Any],
    ) -> list[str]:
        plan = AskInvestigationPlanner.build(analysis, files, context)
        return [
            *plan["questions"],
            *plan["missing_evidence"],
        ]

    @staticmethod
    def infer_tabular_semantics(
        analysis: dict[str, Any], inspection: dict[str, Any]
    ) -> dict[str, Any]:
        # Column meaning belongs to a capability selected by a future plan,
        # never to the generic preparation workflow.
        return {}

    @staticmethod
    def build_plan(
        analysis: dict[str, Any], files: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return AskInvestigationPlanner.build(analysis, files, context)

    @classmethod
    def execute(
        cls, analysis: dict[str, Any], files: list[dict[str, Any]]
    ) -> dict[str, Any]:
        plan = analysis.get("plan") or {}
        if not isinstance(plan, dict):
            plan = AskInvestigationPlanner.build(
                analysis, files, analysis.get("context") or {}
            )
        capability_results = AskCapabilityRegistry.execute(
            plan.get("capabilities", []), analysis, files
        )
        knowledge: dict[str, Any] = {
            "goal": analysis["objective"],
            "expected_decision": plan.get("expected_decision"),
            "plan": plan,
            "facts": [],
            "metrics": [],
            "findings": [],
            "risks": [],
            "opportunities": [],
            "recommendations": [],
            "pending_investigations": list(plan.get("missing_evidence", [])),
            "supporting_evidence": [],
            "working_dataset": [],
            "confidence": "Media",
            "trace": [{
                "step": "Objetivo comprendido",
                "status": "completed",
            }],
        }
        for result in capability_results:
            for key in (
                "facts", "metrics", "findings", "risks", "opportunities",
                "recommendations", "pending_investigations",
                "supporting_evidence", "working_dataset", "trace",
            ):
                knowledge[key].extend(result.get(key, []))
        knowledge["trace"].append({
            "step": "Conocimiento estructurado consolidado",
            "status": "completed",
        })
        if knowledge["pending_investigations"]:
            knowledge["confidence"] = "Baja"
        elif knowledge["facts"] or knowledge["findings"]:
            knowledge["confidence"] = "Alta"
        knowledge["summary"] = {
            "facts": len(knowledge["facts"]),
            "metrics": len(knowledge["metrics"]),
            "findings": len(knowledge["findings"]),
            "risks": len(knowledge["risks"]),
            "opportunities": len(knowledge["opportunities"]),
            "pending_investigations": len(
                knowledge["pending_investigations"]
            ),
        }
        return knowledge

    @classmethod
    def build_artifacts(
        cls, knowledge: dict[str, Any], specification: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Render only the artifact contract requested by the conversation."""
        requested = specification.get("artifacts")
        if isinstance(requested, list):
            artifacts = [
                cls._normalize_artifact(artifact, index)
                for index, artifact in enumerate(requested)
                if isinstance(artifact, dict)
            ]
            source_file_ids = cls._source_file_ids(knowledge)
            for artifact in artifacts:
                artifact["metadata"].setdefault(
                    "source_file_ids", source_file_ids
                )
            return artifacts
        sections = specification.get("sections") or cls._knowledge_sections(
            knowledge
        )
        artifacts = [{
            "key": "requested-document",
            "type": "document",
            "title": specification.get("title") or "Entregable solicitado",
            "description": specification.get("description") or (
                "Generado desde el conocimiento de esta investigación."
            ),
            "blocks": [
                {
                    "type": section.get("type", "text"),
                    "title": section.get("title", "Sección"),
                    "content": section.get("content", ""),
                }
                for section in sections
            ],
            "metadata": {
                "confidence": knowledge.get("confidence"),
                "source_file_ids": cls._source_file_ids(knowledge),
            },
        }]
        rows = knowledge.get("working_dataset") or []
        if specification.get("include_dataset") and rows:
            artifacts.append({
                "key": "working-dataset",
                "type": "dataset",
                "title": specification.get("dataset_title")
                or "Dataset de trabajo",
                "description": "Estructura definida por la investigación.",
                "blocks": [{
                    "type": "table", "title": "Datos",
                    "schema": cls._dataset_schema(rows), "rows": rows,
                }],
                "metadata": {
                    "row_count": len(rows),
                    "source_file_ids": cls._source_file_ids(knowledge),
                },
            })
        return artifacts

    @staticmethod
    def _normalize_artifact(
        artifact: dict[str, Any], index: int
    ) -> dict[str, Any]:
        return {
            "key": artifact.get("key") or f"artifact-{index + 1}",
            "type": artifact.get("type") or "document",
            "title": artifact.get("title") or f"Entregable {index + 1}",
            "description": artifact.get("description") or "",
            "blocks": artifact.get("blocks") or [],
            "metadata": artifact.get("metadata") or {},
        }

    @staticmethod
    def _knowledge_sections(
        knowledge: dict[str, Any]
    ) -> list[dict[str, Any]]:
        sections = []
        for key, title in (
            ("facts", "Hechos"),
            ("findings", "Hallazgos"),
            ("risks", "Riesgos"),
            ("opportunities", "Oportunidades"),
            ("recommendations", "Recomendaciones"),
            ("pending_investigations", "Investigaciones pendientes"),
        ):
            values = knowledge.get(key) or []
            if values:
                sections.append({
                    "title": title,
                    "type": "list",
                    "content": [
                        value.get("statement", str(value))
                        if isinstance(value, dict) else str(value)
                        for value in values
                    ],
                })
        return sections or [{
            "title": "Estado de la investigación",
            "type": "text",
            "content": (
                "La evidencia fue procesada, pero todavía no produce "
                "conclusiones suficientes."
            ),
        }]

    @staticmethod
    def _dataset_schema(
        rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        columns = list(dict.fromkeys(
            key for row in rows for key in row
        ))
        return [
            {
                "name": column,
                "label": column.replace("_", " ").capitalize(),
                "type": AskAnalysisEngine._column_type(
                    [row.get(column) for row in rows]
                ),
                "editable": False, "sortable": True, "filterable": True,
                "format": "auto",
            }
            for column in columns
        ]

    @staticmethod
    def _column_type(values: list[Any]) -> str:
        present = [value for value in values if value is not None]
        if present and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in present
        ):
            return "number"
        if present and all(isinstance(value, bool) for value in present):
            return "boolean"
        return "text"

    @staticmethod
    def _source_file_ids(knowledge: dict[str, Any]) -> list[int]:
        return sorted({
            item["file_id"]
            for item in knowledge.get("supporting_evidence", [])
            if isinstance(item, dict) and item.get("file_id") is not None
        })
