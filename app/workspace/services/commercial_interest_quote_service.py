import hashlib
import json
from typing import Any

from app.database.transaction import transactional
from app.workspace.repositories.imported_commercial_line_repository import (
    ImportedCommercialLineRepository,
)
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.repositories.quote_line_repository import QuoteLineRepository
from app.workspace.repositories.quote_repository import QuoteRepository
from app.workspace.services.project_access_policy import ProjectAccessPolicy


class CommercialInterestQuoteService:
    @classmethod
    def get_interest(cls, opportunity_id: int) -> dict[str, Any]:
        lines = ImportedCommercialLineRepository.list_for_opportunity(
            opportunity_id
        )
        total = sum(
            float(line["potential_value"])
            for line in lines if line["potential_value"] is not None
        )
        signature = cls._signature(lines)
        latest_quote = QuoteRepository.latest_crm_generated(opportunity_id)
        return {
            "lines": lines,
            "potential_total": total if lines else None,
            "signature": signature,
            "latest_generated_quote": latest_quote,
            "changed_since_quote": bool(
                latest_quote
                and latest_quote.get("source_lines_signature") != signature
            ),
        }

    @classmethod
    @transactional
    def generate_quote(
        cls, opportunity_id: int
    ) -> int:
        ProjectAccessPolicy.require_writable(opportunity_id)
        project = ProjectRepository.get_project(opportunity_id)
        if not project:
            raise ValueError("La oportunidad no existe.")
        interest = cls.get_interest(opportunity_id)
        lines = interest["lines"]
        if not lines:
            raise ValueError(
                "La oportunidad no tiene líneas comerciales importadas."
            )
        revision = QuoteRepository.next_crm_revision(opportunity_id)
        quote_id = QuoteRepository.create_quote(
            project_id=opportunity_id,
            prefix="CRM",
            quote_number=f"{project.get('external_id') or opportunity_id}-V{revision}",
            amount=float(interest["potential_total"] or 0),
            currency_code="COP",
            normalized_amount=float(interest["potential_total"] or 0),
            quote_status="draft",
            revision=revision,
        )
        for index, line in enumerate(lines, start=1):
            QuoteLineRepository.create(
                quote_id,
                brand=line.get("brand"),
                part_number=line.get("part_number"),
                description=line.get("description") or "Línea CRM",
                quantity=1,
                unit_price=float(line.get("potential_value") or 0),
                currency_code="COP",
                imported_commercial_line_id=int(line["id"]),
                display_order=index,
            )
        QuoteRepository.mark_generated_from_crm(
            quote_id, signature=interest["signature"]
        )
        return quote_id

    @staticmethod
    def quote_lines(quote_id: int) -> list[dict[str, Any]]:
        return QuoteLineRepository.list_for_quote(quote_id)

    @staticmethod
    @transactional
    def add_quote_line(
        quote_id: int, *, brand: str | None, part_number: str | None,
        description: str, quantity: float, unit_price: float,
    ) -> int:
        quote = QuoteRepository.get_quote(quote_id)
        if not quote:
            raise ValueError("La cotización no existe.")
        ProjectAccessPolicy.require_writable(quote["project_id"])
        clean_description = str(description or "").strip()
        if not clean_description:
            raise ValueError("La descripción es obligatoria.")
        clean_quantity, clean_price = CommercialInterestQuoteService._numbers(
            quantity, unit_price
        )
        line_id = QuoteLineRepository.create(
            quote_id, brand=str(brand or "").strip() or None,
            part_number=str(part_number or "").strip() or None,
            description=clean_description, quantity=clean_quantity,
            unit_price=clean_price,
        )
        CommercialInterestQuoteService._refresh_total(quote_id)
        return line_id

    @staticmethod
    @transactional
    def update_quote_line(
        line_id: int, *, brand: str | None, part_number: str | None,
        description: str, quantity: float, unit_price: float,
    ) -> int:
        line = QuoteLineRepository.get(line_id)
        if not line:
            raise ValueError("La línea de cotización no existe.")
        quote = QuoteRepository.get_quote(line["quote_id"])
        ProjectAccessPolicy.require_writable(quote["project_id"])
        clean_description = str(description or "").strip()
        if not clean_description:
            raise ValueError("La descripción es obligatoria.")
        clean_quantity, clean_price = CommercialInterestQuoteService._numbers(
            quantity, unit_price
        )
        QuoteLineRepository.update(
            line_id, brand=str(brand or "").strip() or None,
            part_number=str(part_number or "").strip() or None,
            description=clean_description, quantity=clean_quantity,
            unit_price=clean_price,
        )
        CommercialInterestQuoteService._refresh_total(line["quote_id"])
        return int(line["quote_id"])

    @staticmethod
    @transactional
    def delete_quote_line(line_id: int) -> int:
        line = QuoteLineRepository.get(line_id)
        if not line:
            raise ValueError("La línea de cotización no existe.")
        quote = QuoteRepository.get_quote(line["quote_id"])
        ProjectAccessPolicy.require_writable(quote["project_id"])
        QuoteLineRepository.delete(line_id)
        CommercialInterestQuoteService._refresh_total(line["quote_id"])
        return int(line["quote_id"])

    @staticmethod
    def _refresh_total(quote_id: int) -> None:
        total = QuoteLineRepository.total(quote_id)
        QuoteRepository.update_amount(
            quote_id=quote_id, amount=total, normalized_amount=total
        )

    @staticmethod
    def _numbers(quantity: float, price: float) -> tuple[float, float]:
        clean_quantity = float(quantity)
        clean_price = float(price)
        if clean_quantity < 0 or clean_price < 0:
            raise ValueError("Cantidad y precio no pueden ser negativos.")
        return clean_quantity, clean_price

    @staticmethod
    def _signature(lines: list[dict[str, Any]]) -> str:
        evidence = [
            {
                "source_line_key": line["source_line_key"],
                "brand": line.get("brand"),
                "part_number": line.get("part_number"),
                "description": line.get("description"),
                "potential_value": line.get("potential_value"),
            }
            for line in lines
        ]
        return hashlib.sha256(
            json.dumps(
                evidence, ensure_ascii=False, sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
