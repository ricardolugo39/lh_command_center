import json
import re
from typing import Any

import requests

from app.configuration import resolve_settings


class AskOpenAIError(RuntimeError):
    pass


class AskOpenAIService:
    ENDPOINT = "https://api.openai.com/v1/chat/completions"

    @classmethod
    def plan_investigation(
        cls, planning_context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return a dynamic plan; absence of OAuth/API config is non-fatal."""
        settings, _ = resolve_settings(("OPENAI_API_KEY", "OPENAI_MODEL"))
        api_key = settings.get("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            response = requests.post(
                cls.ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.get("OPENAI_MODEL", "gpt-4.1-mini"),
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Planifica una investigación empresarial sin "
                                "asumir dominio, cálculos ni entregables. Usa "
                                "solo capacidades declaradas. Maximiza "
                                "inferencia y pregunta únicamente lo que no "
                                "pueda derivarse. Responde JSON con "
                                "expected_decision, required_information, "
                                "missing_evidence, possible_calculations, "
                                "assumptions, questions, "
                                "inferred_without_question, capabilities, "
                                "potential_outputs y steps. No ejecutes el "
                                "análisis ni produzcas conclusiones."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                planning_context,
                                ensure_ascii=False,
                                default=str,
                            ),
                        },
                    ],
                },
                timeout=45,
            )
            response.raise_for_status()
            result = json.loads(
                response.json()["choices"][0]["message"]["content"]
            )
        except (
            requests.RequestException, KeyError, ValueError,
            json.JSONDecodeError,
        ):
            return None
        return result if isinstance(result, dict) else None

    @classmethod
    def generate(cls, evidence: dict[str, Any]) -> dict[str, Any]:
        settings, _ = resolve_settings(("OPENAI_API_KEY", "OPENAI_MODEL"))
        api_key = settings.get("OPENAI_API_KEY")
        if not api_key:
            raise AskOpenAIError(
                "OPENAI_API_KEY no está configurada. Los cálculos se conservaron."
            )
        model = settings.get("OPENAI_MODEL", "gpt-4.1-mini")
        payload_evidence = {
            **evidence,
            "supporting_rows": evidence.get("supporting_rows", [])[:100],
        }
        try:
            response = requests.post(
                cls.ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": cls._system_prompt()},
                        {
                            "role": "user",
                            "content": json.dumps(
                                payload_evidence, ensure_ascii=False,
                                default=str,
                            ),
                        },
                    ],
                },
                timeout=90,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError) as error:
            raise AskOpenAIError(
                "OpenAI no pudo completar el razonamiento ejecutivo."
            ) from error
        result = cls._normalize_output(result)
        cls._validate_output(result)
        cls._validate_numbers(result, payload_evidence)
        result["_model"] = model
        return result

    @classmethod
    def specify_artifacts(
        cls, knowledge: dict[str, Any], instruction: str
    ) -> dict[str, Any]:
        settings, _ = resolve_settings(("OPENAI_API_KEY", "OPENAI_MODEL"))
        api_key = settings.get("OPENAI_API_KEY")
        if not api_key:
            raise AskOpenAIError(
                "OPENAI_API_KEY no está configurada. El conocimiento se "
                "conservó y el entregable puede generarse después."
            )
        payload = {
            "instruction": instruction,
            "knowledge": {
                **knowledge,
                "working_dataset": knowledge.get(
                    "working_dataset", []
                )[:100],
            },
        }
        try:
            response = requests.post(
                cls.ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.get("OPENAI_MODEL", "gpt-4.1-mini"),
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": cls._artifact_prompt(),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                payload, ensure_ascii=False, default=str
                            ),
                        },
                    ],
                },
                timeout=90,
            )
            response.raise_for_status()
            result = json.loads(
                response.json()["choices"][0]["message"]["content"]
            )
        except (
            requests.RequestException, KeyError, ValueError,
            json.JSONDecodeError,
        ) as error:
            raise AskOpenAIError(
                "OpenAI no pudo definir el entregable solicitado."
            ) from error
        if not isinstance(result, dict):
            raise AskOpenAIError(
                "OpenAI devolvió un contrato de artefactos inválido."
            )
        cls._validate_numbers(result, payload)
        return result

    @staticmethod
    def _system_prompt() -> str:
        return (
            "Eres un analista comercial que consolida conocimiento, no un "
            "generador automático de reportes. Recibes únicamente evidencia "
            "calculada por el sistema. Responde en español con JSON válido y las "
            "claves title (string), confidence (Alta, Media o Baja), "
            "unresolved_questions (lista) y sections (lista ordenada). Cada "
            "sección contiene title, type y content; content puede ser texto o "
            "lista. Decide las secciones según la investigación: no uses una "
            "estructura fija ni asumas dominio, análisis o entregable. Las "
            "secciones representan conocimiento provisional para continuar "
            "la conversación; no un reporte final. "
            "Separa hechos, riesgos y recomendaciones. No inventes entidades ni "
            "números. Distingue evidencia faltante de evidencia negativa: no "
            "afirmes que algo no existe solo porque no fue localizado. Usa las "
            "investigations para explicar fuente esperada, pasos realizados, "
            "causas alternativas y confianza. Si la evidencia requerida no fue "
            "validada, no recomiendes aprobar ni rechazar; recomienda la próxima "
            "investigación necesaria. Todo número escrito debe estar respaldado "
            "por la evidencia. No produzcas HTML ni Markdown."
        )

    @staticmethod
    def _artifact_prompt() -> str:
        return (
            "Transforma conocimiento estructurado en los entregables que el "
            "usuario solicitó. No asumas un dominio ni un formato no pedido. "
            "Responde JSON con artifacts: lista de objetos con key, type, "
            "title, description, blocks y metadata. Los bloques son genéricos: "
            "text con title/content, list con title/content, table con title/"
            "schema/rows o records con title/records. Si se solicita un dataset "
            "puedes responder include_dataset=true además de sections. No "
            "inventes hechos, entidades ni números. Conserva referencias a la "
            "evidencia. No produzcas HTML ni Markdown."
        )

    @staticmethod
    def _validate_output(value: dict[str, Any]) -> None:
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("title"), str)
            or not isinstance(value.get("sections"), list)
            or any(
                not isinstance(section, dict)
                or not isinstance(section.get("title"), str)
                or not isinstance(section.get("type"), str)
                or not isinstance(section.get("content"), (str, list))
                for section in value.get("sections", [])
            )
        ):
            raise AskOpenAIError(
                "OpenAI devolvió una estructura de análisis inválida."
            )
        for section in value["sections"]:
            if isinstance(section["content"], list) and any(
                not isinstance(item, str) for item in section["content"]
            ):
                raise AskOpenAIError(
                    "OpenAI devolvió hallazgos con formato inválido."
                )

    @staticmethod
    def _normalize_output(value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict) or value.get("sections") is not None:
            return value
        legacy_fields = (
            ("Resumen ejecutivo", "executive_summary"),
            ("Hallazgos", "key_findings"),
            ("Riesgos", "commercial_risks"),
            ("Oportunidades", "opportunities"),
            ("Preguntas pendientes", "questions_before_approval"),
            ("Acciones recomendadas", "recommended_actions"),
        )
        sections = [
            {
                "title": title,
                "type": "list" if isinstance(value.get(key), list) else "text",
                "content": value[key],
            }
            for title, key in legacy_fields if value.get(key)
        ]
        return {
            **value,
            "title": value.get("title") or "Análisis ejecutivo",
            "confidence": value.get("confidence"),
            "unresolved_questions": value.get(
                "questions_before_approval", []
            ),
            "sections": sections,
        }

    @staticmethod
    def _validate_numbers(result: dict, evidence: dict) -> None:
        pattern = r"(?<![\w])[-+]?\d+(?:[.,]\d+)?"
        evidence_numbers = [
            float(value.replace(",", "."))
            for value in re.findall(
                pattern,
                json.dumps(evidence, ensure_ascii=False, default=str),
            )
        ]
        output_values = re.findall(
            pattern, json.dumps(result, ensure_ascii=False)
        )
        unexpected = [
            value for value in output_values
            if not AskOpenAIService._number_is_supported(
                value, evidence_numbers
            )
        ]
        if unexpected:
            raise AskOpenAIError(
                "OpenAI incluyó cifras no respaldadas por la evidencia."
            )

    @staticmethod
    def _number_is_supported(
        output_value: str, evidence_numbers: list[float]
    ) -> bool:
        number = float(output_value.replace(",", "."))
        decimals = (
            len(output_value.rsplit(".", 1)[1])
            if "." in output_value
            else len(output_value.rsplit(",", 1)[1])
            if "," in output_value else 0
        )
        tolerance = .5 * (10 ** -decimals)
        for evidence in evidence_numbers:
            for scale in (1, 1_000, 1_000_000, 1_000_000_000):
                if abs(number - evidence / scale) <= tolerance:
                    return True
        return False
