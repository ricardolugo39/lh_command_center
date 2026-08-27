from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from app.database.transaction import transactional
from app.workspace.repositories.opportunity_import_repository import (
    OpportunityImportRepository,
)


class OpportunityImportProfileError(ValueError):
    pass


class OpportunityImportProfileService:
    """Validates declarative mappings without permitting executable rules."""

    CONCEPT_REGISTRY = {
        "external_opportunity_id": {
            "type": "text", "required": True, "scope": "opportunity",
            "ownership": "identity",
        },
        "origin_reference": {
            "type": "text", "required": False, "scope": "opportunity",
            "ownership": "identity",
        },
        "customer_identity": {
            "type": "text", "required": True, "scope": "opportunity",
            "ownership": "resolution",
        },
        "opportunity_name": {
            "type": "text", "required": True, "scope": "opportunity",
            "ownership": "configurable",
        },
        "objective": {
            "type": "text", "required": False, "scope": "opportunity",
            "ownership": "configurable",
        },
        "seller": {
            "type": "text", "required": False, "scope": "opportunity",
            "ownership": "configurable",
        },
        "stage": {
            "type": "controlled", "required": False, "scope": "opportunity",
            "ownership": "configurable",
        },
        "probability": {
            "type": "decimal", "required": False, "scope": "opportunity",
            "ownership": "source_fact",
        },
        "potential_value": {
            "type": "decimal", "required": False, "scope": "opportunity",
            "ownership": "source_fact",
        },
        "currency": {
            "type": "text", "required": False, "scope": "opportunity",
            "ownership": "source_fact",
        },
        "close_date": {
            "type": "date", "required": False, "scope": "opportunity",
            "ownership": "source_fact",
        },
        "source_row_id": {
            "type": "text", "required": False, "scope": "row",
            "ownership": "traceability",
        },
        "source_updated_at": {
            "type": "date", "required": False, "scope": "row",
            "ownership": "source_fact",
        },
        "customer_site": {
            "type": "text", "required": False, "scope": "opportunity",
            "ownership": "source_fact",
        },
        "customer_phone": {
            "type": "text", "required": False, "scope": "opportunity",
            "ownership": "resolution",
        },
        "customer_mobile": {
            "type": "text", "required": False, "scope": "opportunity",
            "ownership": "resolution",
        },
        "customer_city": {
            "type": "text", "required": False, "scope": "opportunity",
            "ownership": "resolution",
        },
        "creator": {
            "type": "text", "required": False, "scope": "opportunity",
            "ownership": "source_fact",
        },
        "crm_status": {
            "type": "controlled", "required": False, "scope": "opportunity",
            "ownership": "source_fact",
        },
        "crm_stage": {
            "type": "controlled", "required": False, "scope": "opportunity",
            "ownership": "source_fact",
        },
        "priority": {
            "type": "integer", "required": False, "scope": "opportunity",
            "ownership": "source_fact",
        },
        "brand": {
            "type": "text", "required": False, "scope": "row",
            "ownership": "source_fact",
        },
        "product_code": {
            "type": "text", "required": False, "scope": "row",
            "ownership": "source_fact",
        },
        "product_description": {
            "type": "text", "required": False, "scope": "row",
            "ownership": "source_fact",
        },
        "line_potential_value": {
            "type": "decimal", "required": False, "scope": "row",
            "ownership": "source_fact",
        },
    }
    CONCEPTS = frozenset(CONCEPT_REGISTRY)
    REQUIRED = frozenset({
        "external_opportunity_id", "customer_identity", "opportunity_name",
    })

    @staticmethod
    def _trim(value: Any, _options: dict[str, Any]) -> str | None:
        if value is None:
            return None
        result = str(value).strip()
        return result or None

    @staticmethod
    def _decimal(value: Any, _options: dict[str, Any]) -> float | None:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).replace(",", "").strip())

    @staticmethod
    def _integer(value: Any, _options: dict[str, Any]) -> int | None:
        if value is None or str(value).strip() == "":
            return None
        return int(float(str(value).strip()))

    @staticmethod
    def _date(value: Any, _options: dict[str, Any]) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        if hasattr(value, "date"):
            value = value.date()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return datetime.fromisoformat(str(value).strip()).date().isoformat()

    @staticmethod
    def _controlled(value: Any, options: dict[str, Any]) -> Any:
        if value is None:
            return None
        mapping = options.get("mapping", {})
        key = str(value).strip()
        return mapping.get(key, mapping.get(key.lower(), options.get("default", key)))

    TRANSFORMATIONS: dict[str, Callable[[Any, dict[str, Any]], Any]] = {
        "trim_text": _trim,
        "normalize_blank": _trim,
        "parse_decimal": _decimal,
        "parse_integer": _integer,
        "parse_date": _date,
        "controlled_value": _controlled,
        "stage_mapping": _controlled,
        "stable_customer_key": _trim,
        "seller_resolution": _trim,
    }

    @classmethod
    def validate(
        cls, mapping: dict[str, str],
        transformations: dict[str, Any] | None = None,
        grouping: dict[str, Any] | None = None,
    ) -> None:
        unknown = set(mapping) - cls.CONCEPTS
        required = set(cls.REQUIRED)
        if (grouping or {}).get("name_strategy"):
            required.discard("opportunity_name")
        missing = required - set(mapping)
        if unknown:
            raise OpportunityImportProfileError(
                "Conceptos canónicos desconocidos: " + ", ".join(sorted(unknown))
            )
        if missing:
            raise OpportunityImportProfileError(
                "Faltan conceptos requeridos: " + ", ".join(sorted(missing))
            )
        if any(not str(header).strip() for header in mapping.values()):
            raise OpportunityImportProfileError(
                "Cada concepto debe apuntar a una columna de origen."
            )
        for rules in (transformations or {}).values():
            for rule in cls._rules(rules):
                if rule["name"] not in cls.TRANSFORMATIONS:
                    raise OpportunityImportProfileError(
                        f"Transformación no permitida: {rule['name']}"
                    )

    @classmethod
    def transform(cls, value: Any, rules: Any) -> Any:
        result = value
        for rule in cls._rules(rules):
            function = cls.TRANSFORMATIONS.get(rule["name"])
            if not function:
                raise OpportunityImportProfileError(
                    f"Transformación no permitida: {rule['name']}"
                )
            result = function(result, rule.get("options", {}))
        return result

    @staticmethod
    def _rules(value: Any) -> list[dict[str, Any]]:
        if not value:
            return []
        if isinstance(value, str):
            return [{"name": value}]
        if isinstance(value, dict):
            return [value]
        return [
            {"name": item} if isinstance(item, str) else item
            for item in value
        ]

    @classmethod
    @transactional
    def create_profile(
        cls, name: str, *, mapping: dict[str, str],
        transformations: dict[str, Any] | None = None,
        grouping: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        ownership: dict[str, Any] | None = None,
        created_by: str = "system", activate: bool = False,
    ) -> int:
        cls.validate(mapping, transformations, grouping)
        profile_id = OpportunityImportRepository.create_profile(
            name, created_by=created_by
        )
        OpportunityImportRepository.add_version(
            profile_id, mapping=mapping, transformations=transformations,
            grouping=grouping, validation=validation, ownership=ownership,
            created_by=created_by,
        )
        if activate:
            OpportunityImportRepository.activate(
                profile_id, updated_by=created_by
            )
        return profile_id

    @classmethod
    def active_profile(cls) -> dict[str, Any] | None:
        profile = OpportunityImportRepository.active_version()
        if profile:
            cls.validate(
                profile["column_mapping"],
                profile["transformation_rules"],
                profile["grouping_configuration"],
            )
        return profile
