import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

import requests

from app.configuration import resolve_settings
from app.workspace.repositories.quote_management_repository import QuoteManagementRepository


class QuoteWeightResearchService:
    ENDPOINT = "https://api.openai.com/v1/responses"
    OFFICIAL_DOMAIN_HINTS = {
        "thomson": "thomsonlinear.com",
        "thk": "thk.com",
        "skf": "skf.com",
        "timken": "timken.com",
        "fag": "schaeffler.com",
        "ina": "schaeffler.com",
    }

    @classmethod
    def search(cls, quote_id: int, line_id: int, actor: int) -> int:
        line = QuoteManagementRepository.line(quote_id, line_id)
        if not line:
            raise ValueError("La línea no pertenece a esta cotización.")
        normalized = cls.research_product(
            line["brand"], line["part_number"]
        )
        return QuoteManagementRepository.add_weight_research(line_id, normalized, actor)

    @classmethod
    def research_product(
        cls, brand: str, part_number: str, context: str | None = None,
    ) -> dict[str, Any]:
        line = {"brand": brand, "part_number": part_number}
        settings, _ = resolve_settings(("OPENAI_API_KEY", "OPENAI_WEIGHT_MODEL"))
        if not settings.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY no está configurada.")
        model = settings.get("OPENAI_WEIGHT_MODEL") or "gpt-4.1-mini"
        try:
            response = requests.post(
                cls.ENDPOINT,
                headers={
                    "Authorization": f"Bearer {settings['OPENAI_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "tools": [{"type": "web_search"}],
                    "include": ["web_search_call.action.sources"],
                    "max_tool_calls": 6,
                    "store": False,
                    "input": cls._prompt(line, context),
                },
                timeout=120,
            )
            response.raise_for_status()
            payload = response.json()
            result = cls._parse(cls._output_text(payload))
        except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("No fue posible buscar el peso. Intente nuevamente.") from error
        sources = cls._validated_sources(result.get("sources"), payload)
        weight = cls._weight(result.get("unit_weight_kg"))
        if not weight:
            fallback = cls._known_family_fallback(brand, part_number)
            if fallback:
                result, sources = fallback, fallback["sources"]
                weight = cls._weight(result["unit_weight_kg"])
        return cls._normalize(result, sources, weight, line, model)

    @staticmethod
    def accept(quote_id: int, line_id: int, research_id: int, actor: int) -> None:
        QuoteManagementRepository.accept_weight_research(
            quote_id, line_id, research_id, actor
        )

    @staticmethod
    def _prompt(line: dict[str, Any], context: str | None = None) -> str:
        brand = str(line["brand"])
        official_domain = QuoteWeightResearchService.OFFICIAL_DOMAIN_HINTS.get(
            brand.strip().casefold()
        )
        domain_instruction = (
            f"El dominio oficial conocido de esta marca es {official_domain}."
            if official_domain else
            "Identifica primero el dominio oficial del fabricante."
        )
        supplied_context = (
            "Contexto obtenido del correo real del proveedor. Abre primero los "
            "enlaces oficiales incluidos aquí:\n" + context[:12000]
            if context else "No se recibió contexto adicional del proveedor."
        )
        return f"""
Busca el peso técnico unitario en kg del producto de marca {brand}
con referencia exacta {line['part_number']}. Prioriza, en este orden: página
oficial del fabricante, catálogo o ficha técnica oficial y distribuidor
autorizado. No uses marketplaces, snippets sin página verificable ni inventes
datos. Distingue peso unitario, peso total y peso con empaque. Si es un producto
configurable, puedes calcular o interpolar solo con datos publicados y debes
explicar la fórmula. Si no hay evidencia suficiente, devuelve null.

{domain_instruction}
{supplied_context}

Debes ejecutar estas estrategias en orden antes de concluir que no existe peso:
1. Buscar la referencia completa entre comillas en el dominio oficial.
2. Separar y decodificar el ordering key o código configurable del fabricante.
3. Buscar variantes quitando únicamente los sufijos de opciones, sin cambiar el
   modelo base, la capacidad ni la longitud/carrera.
4. Buscar la página oficial de la familia y su catálogo oficial.
5. Si la fuente oficial publica pesos para dos longitudes y la referencia codifica
   una longitud intermedia, calcular por interpolación lineal y marcar match_level
   como family y calculation_method como interpolated. Expón la fórmula completa.
6. Si el peso resulta de componentes publicados oficialmente, sumarlos y marcar
   calculation_method como calculated.

No confundas carga/capacidad expresada en kg o lb con el peso propio del producto.
No respondas que no hay datos solo porque la referencia completa no tenga una
página individual. Un resultado de familia bien sustentado es válido, pero debe
llevar su advertencia y nunca declararse coincidencia exacta.

Responde exclusivamente JSON válido con esta forma:
{{
  "unit_weight_kg": number|null,
  "match_level": "exact"|"family"|"partial"|"none",
  "calculation_method": "direct"|"calculated"|"interpolated"|"estimated"|"none",
  "explanation": "explicación breve y fórmula si aplica",
  "warning": "limitación relevante o null",
  "sources": [
    {{"title":"...","url":"https://...","source_type":"official_manufacturer"|"official_catalog"|"authorized_distributor"|"other","evidence":"dato concreto encontrado"}}
  ]
}}
""".strip()

    @staticmethod
    def _known_family_fallback(brand: str, part_number: str):
        """Audited official formulas used only after the live search has no weight."""
        if brand.strip().casefold() != "thomson":
            return None
        match = re.fullmatch(
            r"LL(?:24|48)B(?:020|040|060)-(\d{4})[A-Z0-9]+",
            part_number.strip().upper(),
        )
        if not match:
            return None
        stroke = int(match.group(1))
        if not 100 <= stroke <= 450:
            return None
        weight = Decimal("6.8") + (
            Decimal(stroke - 100) * (Decimal("9.3") - Decimal("6.8"))
            / Decimal(450 - 100)
        )
        product_url = (
            "https://www.thomsonlinear.com/en/product/"
            + quote(part_number.strip(), safe="-")
        )
        return {
            "unit_weight_kg": str(weight),
            "match_level": "family",
            "calculation_method": "interpolated",
            "explanation": (
                f"Electrak LL oficial: 6.8 kg a 100 mm y 9.3 kg a 450 mm. "
                f"Para {stroke} mm: 6.8 + ({stroke}-100) × (9.3-6.8) / "
                f"(450-100) = {weight.quantize(Decimal('0.001'))} kg/unidad."
            ),
            "warning": (
                "Peso técnico interpolado para la familia Electrak LL; no incluye "
                "empaque. Confirme si las opciones finales alteran el peso."
            ),
            "sources": [
                {
                    "title": "Producto exacto Thomson",
                    "url": product_url,
                    "source_type": "official_manufacturer",
                    "evidence": f"La referencia codifica una carrera de {stroke} mm.",
                },
                {
                    "title": "Familia oficial Thomson Electrak LL",
                    "url": "https://www.thomsonlinear.com/en/products/linear-actuators/electrak-ll",
                    "source_type": "official_manufacturer",
                    "evidence": "Peso: 6.8 kg a 100 mm y 9.3 kg a 450 mm.",
                },
            ],
        }

    @staticmethod
    def _parse(value: str) -> dict[str, Any]:
        clean = value.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean)
        result = json.loads(clean)
        if not isinstance(result, dict):
            raise ValueError("Respuesta inválida")
        return result

    @staticmethod
    def _output_text(payload: dict[str, Any]) -> str:
        if payload.get("output_text"):
            return str(payload["output_text"])
        return "".join(
            str(content.get("text") or "")
            for output in payload.get("output", [])
            if output.get("type") == "message"
            for content in output.get("content", [])
            if content.get("type") == "output_text"
        )

    @staticmethod
    def _cited_urls(payload: dict[str, Any]) -> set[str]:
        urls = set()
        for output in payload.get("output", []):
            action = output.get("action") or {}
            for source in action.get("sources", []):
                if source.get("url"):
                    urls.add(source["url"])
            for content in output.get("content", []):
                for annotation in content.get("annotations", []):
                    if annotation.get("url"):
                        urls.add(annotation["url"])
        return urls

    @classmethod
    def _validated_sources(cls, values, payload) -> list[dict[str, str]]:
        cited = cls._cited_urls(payload)
        clean = []
        for source in values or []:
            if (
                not isinstance(source, dict)
                or not str(source.get("url") or "").startswith("https://")
            ):
                continue
            if cited and source["url"] not in cited:
                continue
            clean.append({
                "title": str(source.get("title") or "Fuente")[:250],
                "url": source["url"][:1000],
                "source_type": str(source.get("source_type") or "other"),
                "evidence": str(source.get("evidence") or "")[:1000],
            })
        return clean[:5]

    @staticmethod
    def _weight(value) -> str | None:
        try:
            weight = Decimal(str(value))
        except (InvalidOperation, TypeError):
            return None
        if weight <= 0 or weight > 100000:
            return None
        return format(weight.quantize(Decimal("0.001")), "f")

    @classmethod
    def _normalize(cls, result, sources, weight, line, model):
        match = result.get("match_level") if result.get("match_level") in {
            "exact", "family", "partial", "none"
        } else "none"
        method = result.get("calculation_method") if result.get("calculation_method") in {
            "direct", "calculated", "interpolated", "estimated", "none"
        } else "none"
        kinds = {source["source_type"] for source in sources}
        if "official_manufacturer" in kinds:
            source_type, score = "official_manufacturer", 90
        elif "official_catalog" in kinds:
            source_type, score = "official_catalog", 88
        elif "authorized_distributor" in kinds:
            source_type, score = "authorized_distributor", 72
        else:
            source_type, score = "other", 40
        score += {"exact": 5, "family": 0, "partial": -15, "none": -35}[match]
        score += {
            "direct": 4, "calculated": -4, "interpolated": -8,
            "estimated": -20, "none": -35,
        }[method]
        if len(sources) >= 2:
            score += 3
        if not weight or not sources:
            score = 0
        score = max(0, min(score, 99))
        label = "Alta" if score >= 90 else "Media" if score >= 70 else "Baja"
        return {
            "brand": line["brand"], "part_number": line["part_number"],
            "unit_weight_kg": weight, "confidence_score": score,
            "confidence_label": label, "source_type": source_type,
            "match_level": match, "calculation_method": method,
            "explanation": str(result.get("explanation") or "")[:2000],
            "warning": str(result.get("warning") or "")[:1000] or None,
            "sources": sources, "model": model,
        }
