import re
from typing import Any

from app.database.transaction import transactional
from app.workspace.repositories.ask_context_repository import (
    AskContextRepository,
)
from app.workspace.repositories.ask_repository import AskRepository
from app.workspace.services.ask_file_service import AskFileService
from app.workspace.services.ask_analysis_engine import AskAnalysisEngine


class AskAccessError(ValueError):
    pass


class AskPreparationService:
    @classmethod
    @transactional
    def create(cls, objective: str, user_id: int) -> int:
        clean = str(objective or "").strip()
        if not clean:
            raise ValueError("Describa qué desea analizar.")
        analysis_id = AskRepository.create_analysis({
            "title": cls._title(clean), "objective": clean,
            "assumptions": AskAnalysisEngine.initial_assumptions(clean),
            "created_by_user_id": user_id,
        })
        AskRepository.add_message(analysis_id, {
            "role": "user", "content": clean,
            "clarification_type": "objective",
        })
        return analysis_id

    @classmethod
    @transactional
    def refresh(cls, analysis_id: int) -> dict[str, Any]:
        analysis = cls.require_editable(analysis_id)
        files = AskRepository.list_files(analysis_id)
        context = dict(analysis["context"])
        context = cls._resolve_context(analysis, context)
        mappings = {}
        assumptions = {}
        plan = AskAnalysisEngine.build_plan(analysis, files, context)
        blocking = cls._blocking_reasons(
            analysis, files, context, mappings, assumptions, plan
        )
        status = "ready" if not blocking else "draft"
        AskRepository.update(analysis_id, {
            "context": context, "mappings": mappings,
            "assumptions": assumptions, "plan": plan,
            "blocking_reasons": blocking, "status": status,
            "lifecycle_status": (
                "waiting_clarification" if blocking else "draft"
            ),
        })
        return cls.page(analysis_id)

    @classmethod
    @transactional
    def update(
        cls, analysis_id: int, values: dict[str, Any]
    ) -> dict[str, Any]:
        analysis = cls.require_editable(analysis_id)
        objective = str(values.get("objective") or "").strip()
        if not objective:
            raise ValueError("El objetivo es obligatorio.")
        context = dict(analysis["context"])
        selected_customer = values.get("customer_id")
        if selected_customer == "exclude":
            customer_id = None
            context.update({
                "customer_excluded": True, "customer_candidates": [],
                "customer_status": "No disponible",
            })
        elif selected_customer:
            customer = AskContextRepository.customer(int(selected_customer))
            if not customer:
                raise ValueError("El cliente seleccionado no existe.")
            customer_id = customer["id"]
            context.update({
                "customer_excluded": False, "customer": customer,
                "customer_candidates": [], "customer_status": "Confirmado",
            })
        else:
            customer_id = analysis.get("customer_id")
        site_id = str(values.get("customer_site_id") or "").strip() or None
        context["site_scope"] = str(
            values.get("site_scope") or context.get("site_scope") or ""
        )
        mappings = {}
        assumptions = {}
        focus = str(values.get("focus") or "").strip() or None
        notes = str(values.get("pasted_notes") or "").strip()
        if notes and notes != context.get("pasted_notes"):
            context["pasted_notes"] = notes
            AskRepository.add_message(analysis_id, {
                "role": "user", "content": notes,
                "clarification_type": "supporting_notes",
            })
        if focus and focus != analysis.get("focus"):
            AskRepository.add_message(analysis_id, {
                "role": "user", "content": focus,
                "clarification_type": "analysis_focus",
                "resolved_action": "plan_updated",
            })
        AskRepository.update(analysis_id, {
            "objective": objective, "title": cls._title(objective),
            "focus": focus, "customer_id": customer_id,
            "customer_site_id": site_id, "context": context,
            "mappings": mappings, "assumptions": assumptions,
        })
        return cls.refresh(analysis_id)

    @classmethod
    def page(cls, analysis_id: int) -> dict[str, Any]:
        analysis = AskRepository.get(analysis_id)
        if not analysis:
            raise ValueError("El análisis no existe.")
        artifacts = AskRepository.list_artifacts(analysis_id)
        files = AskRepository.list_files(analysis_id)
        for file in files:
            file["used_by"] = [
                {
                    "key": artifact["key"],
                    "title": artifact["title"],
                }
                for artifact in artifacts
                if file["id"] in (
                    artifact.get("metadata", {}).get(
                        "source_file_ids", []
                    )
                )
            ]
        return {
            "analysis": analysis,
            "files": files,
            "messages": AskRepository.list_messages(analysis_id),
            "artifacts": artifacts,
        }

    @classmethod
    def require_access(
        cls, analysis_id: int, user: dict[str, Any]
    ) -> dict[str, Any]:
        analysis = AskRepository.get(analysis_id)
        if not analysis:
            raise ValueError("El análisis no existe.")
        if (
            analysis["created_by_user_id"] != user["id"]
            and user["role"] not in {"administrator", "commercial_management"}
        ):
            raise AskAccessError("No tiene acceso a este análisis.")
        return analysis

    @classmethod
    def require_editable(cls, analysis_id: int) -> dict[str, Any]:
        analysis = AskRepository.get(analysis_id)
        if not analysis:
            raise ValueError("El análisis no existe.")
        if analysis["status"] in {"running", "completed"}:
            raise ValueError(
                "Esta versión está cerrada. Cree una nueva versión para ajustar."
            )
        return analysis

    @classmethod
    @transactional
    def select_customer(cls, analysis_id: int, customer_id: int) -> None:
        analysis = cls.require_editable(analysis_id)
        customer = AskContextRepository.customer(customer_id)
        if not customer:
            raise ValueError("El cliente seleccionado no existe.")
        context = dict(analysis.get("context") or {})
        context.update({
            "customer": customer,
            "customer_status": "Confirmado",
            "customer_candidates": [],
            "customer_excluded": False,
        })
        AskRepository.update(analysis_id, {
            "customer_id": customer_id,
            "context": context,
        })

    @classmethod
    @transactional
    def reanalyze(
        cls, analysis_id: int, user_id: int
    ) -> int:
        previous = AskRepository.get(analysis_id)
        if not previous or previous["status"] != "completed":
            raise ValueError("Solo puede versionar un análisis completado.")
        root = previous["root_analysis_id"] or previous["id"]
        new_id = AskRepository.create_analysis({
            "root_analysis_id": root, "parent_analysis_id": previous["id"],
            "version": AskRepository.next_version(root),
            "title": previous["title"], "objective": previous["objective"],
            "focus": None, "customer_id": previous["customer_id"],
            "customer_site_id": previous["customer_site_id"],
            "context": previous["context"], "mappings": {},
            "assumptions": previous["assumptions"], "plan": previous["plan"],
            "created_by_user_id": user_id,
        })
        new_mappings = {}
        file_id_map = {}
        for file in AskRepository.list_files(previous["id"]):
            new_file_id = AskRepository.add_file(new_id, {
                **file, "inspection": file["inspection"],
            })
            file_id_map[file["id"]] = new_file_id
            new_mappings[str(new_file_id)] = previous["mappings"].get(
                str(file["id"]), {}
            )
        AskRepository.update(new_id, {
            "mappings": new_mappings,
            "evidence": cls._remap_file_ids(previous["evidence"], file_id_map),
            "ai_response": previous["ai_response"],
        })
        copied_artifacts = []
        for artifact in AskRepository.list_artifacts(previous["id"]):
            copied = dict(artifact)
            metadata = dict(copied.get("metadata") or {})
            metadata["source_file_ids"] = [
                file_id_map.get(file_id, file_id)
                for file_id in metadata.get("source_file_ids", [])
            ]
            copied["metadata"] = metadata
            copied_artifacts.append(copied)
        AskRepository.replace_artifacts(new_id, copied_artifacts)
        for message in AskRepository.list_messages(previous["id"]):
            AskRepository.add_message(new_id, {
                "role": message["role"], "content": message["content"],
                "clarification_type": message.get("clarification_type"),
                "related_entity_type": message.get("related_entity_type"),
                "related_entity_id": message.get("related_entity_id"),
                "resolved_action": message.get("resolved_action"),
            })
        AskRepository.add_message(new_id, {
            "role": "system",
            "content": f"Nueva versión desde el análisis {previous['id']}.",
            "clarification_type": "versioning",
        })
        return new_id

    @classmethod
    @transactional
    def evidence_target(cls, analysis_id: int, user_id: int) -> int:
        """Return an editable version; completed analyses are versioned."""
        analysis = AskRepository.get(analysis_id)
        if not analysis:
            raise ValueError("El análisis no existe.")
        if analysis["status"] == "completed":
            return cls.reanalyze(analysis_id, user_id)
        if analysis["status"] == "running":
            raise ValueError("Espere a que finalice la ejecución actual.")
        return analysis_id

    @classmethod
    @transactional
    def continue_investigation(
        cls, analysis_id: int, user_id: int, message: str
    ) -> int:
        content = str(message or "").strip()
        if not content:
            raise ValueError("Escriba una instrucción para continuar.")
        analysis = AskRepository.get(analysis_id)
        if not analysis:
            raise ValueError("El análisis no existe.")
        target_id = analysis_id
        if analysis["status"] == "completed":
            target_id = cls.reanalyze(analysis_id, user_id)
            analysis = AskRepository.get(target_id)
        elif analysis["status"] == "running":
            raise ValueError(
                "Espere a que finalice la ejecución actual."
            )
        context = dict((analysis or {}).get("context") or {})
        directives = list(context.get("conversation_directives") or [])
        directives.append(content)
        context["conversation_directives"] = directives
        AskRepository.add_message(target_id, {
            "role": "user", "content": content,
            "clarification_type": "investigation_instruction",
            "resolved_action": "analysis_revised",
        })
        AskRepository.update(target_id, {
            "focus": content, "context": context,
            "lifecycle_status": "draft", "error_message": None,
        })
        cls.refresh(target_id)
        return target_id

    @classmethod
    def _resolve_context(
        cls, analysis: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        if analysis.get("customer_id"):
            customer = AskContextRepository.customer(analysis["customer_id"])
            context.update({
                "customer": customer, "customer_status": "Confirmado",
                "customer_candidates": [],
            })
            sites = AskContextRepository.customer_sites(
                customer["erp_customer_id"]
            ) if customer and customer.get("erp_customer_id") else []
            context["customer_sites"] = sites
            cls._infer_site_scope(context, sites)
            cls._resolve_brands(analysis, context)
            return context
        if context.get("customer_excluded"):
            return context
        resolution_text = str(
            analysis.get("focus") or analysis["objective"]
        )
        tokens = cls._tokens(resolution_text)
        candidates = AskContextRepository.customer_candidates(tokens)
        context["customer_candidates"] = candidates
        if len(candidates) == 1:
            customer = candidates[0]
            context.update({
                "customer": customer, "customer_status": "Detectado",
                "customer_candidates": [],
            })
            analysis["customer_id"] = customer["id"]
            AskRepository.update(analysis["id"], {
                "customer_id": customer["id"],
            })
            context["customer_sites"] = AskContextRepository.customer_sites(
                customer["erp_customer_id"]
            ) if customer.get("erp_customer_id") else []
            cls._infer_site_scope(context, context["customer_sites"])
        elif len(candidates) > 1:
            context["customer_status"] = "Requiere confirmación"
        else:
            context["customer_status"] = "No disponible"
        cls._resolve_brands(analysis, context)
        return context

    @classmethod
    def _resolve_brands(
        cls, analysis: dict[str, Any], context: dict[str, Any]
    ) -> None:
        brands = AskContextRepository.brand_candidates(cls._tokens(" ".join([
            analysis["objective"], str(analysis.get("focus") or ""),
            *[
                str(item) for item in context.get(
                    "conversation_directives", []
                )
            ],
        ])))
        if brands:
            context["brands"] = brands
            context["brand_status"] = (
                "Detectado" if len(brands) == 1 else "Requiere confirmación"
            )

    @staticmethod
    def _infer_site_scope(context: dict[str, Any], sites: list[dict]) -> None:
        if len(sites) > 1 and not context.get("site_scope"):
            context["site_scope"] = "all"
            context["site_scope_status"] = "Inferido por Ask"

    @staticmethod
    def _merge_mappings(
        current: dict, files: list[dict], analysis: dict | None = None
    ) -> dict:
        result = dict(current)
        analysis = analysis or {}
        for file in files:
            if file["processing_status"] != "processed":
                continue
            key = str(file["id"])
            inspection = file["inspection"]
            proposed = AskAnalysisEngine.infer_tabular_semantics(
                analysis, inspection
            )
            file_mappings = result.setdefault(key, {})
            for concept, inference in proposed.items():
                if file_mappings.get(concept, {}).get("status") != "confirmed":
                    file_mappings[concept] = inference
        return result

    @staticmethod
    def _form_mappings(current: dict, files: list[dict],
                       values: dict[str, Any]) -> dict:
        result = dict(current)
        for file in files:
            key = str(file["id"])
            result.setdefault(key, {})
            concepts = set(result[key])
            prefix = f"mapping_{key}_"
            concepts.update(
                field[len(prefix):] for field in values
                if field.startswith(prefix)
            )
            for concept in concepts:
                column = str(values.get(f"mapping_{key}_{concept}") or "").strip()
                if column:
                    result[key][concept] = {
                        "column": column,
                        "status": (
                            "confirmed"
                            if values.get(f"confirm_{key}_{concept}")
                            else "requires_confirmation"
                        ),
                    }
                else:
                    result[key].pop(concept, None)
        return result

    @classmethod
    def _form_assumptions(
        cls, current: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        result = dict(current)
        for key, current_value in current.items():
            field = f"assumption_{key}"
            if field not in values:
                continue
            value = values.get(field)
            if isinstance(current_value, bool):
                result[key] = str(value).casefold() in {
                    "1", "true", "yes", "si", "sí",
                }
            elif isinstance(current_value, int):
                result[key] = cls._positive_int(value, current_value)
            elif isinstance(current_value, float):
                result[key] = cls._positive_float(value, current_value)
            else:
                result[key] = str(value or "").strip()
        return result

    @classmethod
    def _blocking_reasons(
        cls, analysis, files, context, mappings, assumptions,
        plan: dict[str, Any],
    ) -> list[str]:
        reasons = []
        if not analysis["objective"].strip():
            reasons.append("Debe definir el objetivo del análisis.")
        failed = [file for file in files if file["processing_status"] == "failed"]
        if failed:
            reasons.append("Hay archivos que no pudieron procesarse.")
        if context.get("customer_candidates"):
            reasons.append("Debe seleccionar el cliente correcto.")
        sites = context.get("customer_sites", [])
        if len(sites) > 1 and not (
            analysis.get("customer_site_id") or context.get("site_scope") == "all"
        ):
            reasons.append("Debe indicar si incluye todas las sedes o una sede.")
        return reasons

    @classmethod
    def _remap_file_ids(cls, value: Any, mapping: dict[int, int]) -> Any:
        if isinstance(value, list):
            return [cls._remap_file_ids(item, mapping) for item in value]
        if isinstance(value, dict):
            remapped = {
                key: cls._remap_file_ids(item, mapping)
                for key, item in value.items()
            }
            for key in ("file_id", "source_file_id"):
                if isinstance(remapped.get(key), int):
                    remapped[key] = mapping.get(
                        remapped[key], remapped[key]
                    )
            if isinstance(remapped.get("evidence_file_ids"), list):
                remapped["evidence_file_ids"] = [
                    mapping.get(file_id, file_id)
                    for file_id in remapped["evidence_file_ids"]
                ]
            return remapped
        return value

    @staticmethod
    def _tokens(value: str) -> list[str]:
        ignored = {
            "analiza", "analizar", "revisa", "revisar", "para", "este",
            "esta", "sobre", "quiero", "necesito", "ayudeme", "ayúdeme",
            "cliente", "identidad", "empresa",
        }
        return [
            token for token in re.findall(r"[\wÁÉÍÓÚÑáéíóúñ-]+", value)
            if len(token) >= 4 and token.casefold() not in ignored
        ]

    @staticmethod
    def _title(objective: str) -> str:
        return objective[:90] + ("…" if len(objective) > 90 else "")

    @staticmethod
    def _positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
            return parsed if parsed > 0 else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _positive_float(value: Any, default: float) -> float:
        try:
            parsed = float(value)
            return parsed if parsed > 0 else default
        except (TypeError, ValueError):
            return default
