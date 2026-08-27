from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any

from app.database.transaction import connection_scope
from app.workspace.repositories.opportunity_import_repository import (
    OpportunityImportRepository,
)


class OpportunityIdentityResolutionService:
    """Conservative, explainable production CRM identity resolution."""

    LEGAL_SUFFIXES = (
        ("S", "A", "S"), ("SAS",), ("S", "A"), ("SA",),
        ("LTDA",), ("LIMITADA",), ("S", "EN", "C"),
    )

    @classmethod
    def normalize_text(cls, value: Any) -> str:
        if value is None:
            return ""
        text = unicodedata.normalize("NFKD", str(value))
        text = text.encode("ascii", "ignore").decode().upper()
        return " ".join(re.sub(r"[^A-Z0-9]+", " ", text).split())

    @classmethod
    def normalize_company(cls, value: Any, *, legal: bool = False) -> str:
        normalized = cls.normalize_text(value)
        if not legal:
            return normalized
        tokens = normalized.split()
        changed = True
        while changed and tokens:
            changed = False
            for suffix in cls.LEGAL_SUFFIXES:
                if tuple(tokens[-len(suffix):]) == suffix:
                    tokens = tokens[:-len(suffix)]
                    changed = True
                    break
        return " ".join(tokens)

    @staticmethod
    def normalize_phone(value: Any) -> str:
        digits = re.sub(r"\D", "", str(value or ""))
        return digits if len(digits) >= 7 else ""

    @classmethod
    def resolve_customer(
        cls, *, company_name: str | None, city: str | None,
        phone: str | None, mobile: str | None,
        customer_index: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_name = str(company_name or "").strip()
        normalized = cls.normalize_company(source_name)
        if not normalized:
            return cls._customer_result(
                "blocked", None, "missing_company_name", [],
                display_names=(customer_index or {}).get("display_names"),
            )

        index = customer_index or cls._customer_index()
        exact = index["name"].get(normalized, set())
        if len(exact) == 1:
            return cls._customer_result(
                "matched", next(iter(exact)), "exact_normalized_name", exact,
                display_names=index["display_names"],
            )

        normalized_city = cls.normalize_text(city)
        city_matches = (
            index["city"].get((normalized, normalized_city), set())
            if normalized_city else set()
        )
        if len(city_matches) == 1:
            return cls._customer_result(
                "matched", next(iter(city_matches)),
                "exact_name_and_city", city_matches,
                display_names=index["display_names"],
            )

        phone_matches: set[int] = set()
        for value in (phone, mobile):
            normalized_phone = cls.normalize_phone(value)
            if normalized_phone:
                phone_matches |= index["phone"].get(
                    (normalized, normalized_phone), set()
                )
        if len(phone_matches) == 1:
            return cls._customer_result(
                "matched", next(iter(phone_matches)),
                "exact_name_and_phone", phone_matches,
                display_names=index["display_names"],
            )

        alias = OpportunityImportRepository.customer_alias(normalized)
        if alias:
            return cls._customer_result(
                "matched", int(alias["customer_id"]),
                "confirmed_customer_alias", {int(alias["customer_id"])},
                display_names=index["display_names"],
            )

        legal = index["legal"].get(
            cls.normalize_company(source_name, legal=True), set()
        )
        if len(legal) == 1:
            return cls._customer_result(
                "matched", next(iter(legal)),
                "unique_legal_name_variant", legal,
                display_names=index["display_names"],
            )

        candidates = exact | city_matches | phone_matches | legal
        return cls._customer_result(
            "needs_review", None,
            "ambiguous_customer" if candidates else "customer_not_found",
            candidates,
            display_names=index["display_names"],
        )

    @classmethod
    def resolve_seller(
        cls, source_seller: str | None,
        seller_index: dict[str, set[str]] | None = None,
    ) -> dict[str, Any]:
        display = str(source_seller or "").strip()
        normalized = cls.normalize_text(display)
        if not normalized:
            return {
                "status": "needs_review", "resolved_sales_rep": None,
                "reason": "missing_seller", "candidates": [],
            }
        candidates = seller_index or cls._seller_index()
        exact = candidates.get(normalized, set())
        if len(exact) == 1:
            return {
                "status": "matched",
                "resolved_sales_rep": next(iter(exact)),
                "reason": "exact_normalized_seller", "candidates": sorted(exact),
            }
        alias = OpportunityImportRepository.seller_alias(normalized)
        if alias:
            return {
                "status": "matched",
                "resolved_sales_rep": alias["resolved_sales_rep"],
                "reason": "confirmed_seller_alias",
                "candidates": [alias["resolved_sales_rep"]],
            }
        return {
            "status": "needs_review", "resolved_sales_rep": None,
            "reason": "ambiguous_seller" if exact else "seller_not_found",
            "candidates": sorted(exact),
        }

    @classmethod
    def _seller_index(cls) -> dict[str, set[str]]:
        candidates: dict[str, set[str]] = defaultdict(set)
        for value in OpportunityImportRepository.seller_candidates():
            candidates[cls.normalize_text(value)].add(value)
        return candidates

    @classmethod
    def _customer_index(cls) -> dict[str, Any]:
        name: dict[str, set[int]] = defaultdict(set)
        legal: dict[str, set[int]] = defaultdict(set)
        city: dict[tuple[str, str], set[int]] = defaultdict(set)
        phone: dict[tuple[str, str], set[int]] = defaultdict(set)
        display_names: dict[int, str] = {}
        with connection_scope() as connection:
            customers = connection.execute(
                "SELECT id,name,erp_customer_id FROM ws_customers"
            ).fetchall()
            sites = connection.execute(
                """SELECT nit,razonsocial,ciudad,telefono1,movil
                FROM raw_customers
                WHERE razonsocial IS NOT NULL"""
            ).fetchall()
        customer_by_erp_id = {
            str(row["erp_customer_id"]).strip(): int(row["id"])
            for row in customers if row["erp_customer_id"] is not None
        }
        for row in customers:
            customer_id = int(row["id"])
            display_names[customer_id] = str(row["name"])
            cls._index_name(name, legal, customer_id, row["name"])
        for row in sites:
            customer_id = customer_by_erp_id.get(str(row["nit"]).strip())
            if customer_id is None:
                continue
            normalized_name = cls.normalize_company(row["razonsocial"])
            cls._index_name(name, legal, customer_id, row["razonsocial"])
            normalized_city = cls.normalize_text(row["ciudad"])
            if normalized_name and normalized_city:
                city[(normalized_name, normalized_city)].add(customer_id)
            for source_phone in (row["telefono1"], row["movil"]):
                normalized_phone = cls.normalize_phone(source_phone)
                if normalized_name and normalized_phone:
                    phone[(normalized_name, normalized_phone)].add(customer_id)
        return {
            "name": name, "legal": legal, "city": city, "phone": phone,
            "display_names": display_names,
        }

    @classmethod
    def _index_name(
        cls, name_index: dict[str, set[int]],
        legal_index: dict[str, set[int]], customer_id: int, value: Any,
    ) -> None:
        normalized = cls.normalize_company(value)
        legal = cls.normalize_company(value, legal=True)
        if normalized:
            name_index[normalized].add(customer_id)
        if legal:
            legal_index[legal].add(customer_id)

    @classmethod
    def _customer_result(
        cls, status: str, customer_id: int | None,
        reason: str, candidates: set[int] | list[int],
        display_names: dict[int, str] | None = None,
    ) -> dict[str, Any]:
        ids = sorted(set(candidates) | ({customer_id} if customer_id else set()))
        names: dict[int, str] = display_names or {}
        if ids and not display_names:
            placeholders = ",".join("?" for _ in ids)
            with connection_scope() as connection:
                rows = connection.execute(
                    f"SELECT id,name FROM ws_customers "
                    f"WHERE id IN ({placeholders})",
                    tuple(ids),
                ).fetchall()
            names = {int(row["id"]): str(row["name"]) for row in rows}
        candidate_values = [
            {
                "id": candidate,
                "name": names.get(candidate, str(candidate)),
            }
            for candidate in sorted(set(candidates))
        ]
        return {
            "status": status, "customer_id": customer_id,
            "reason": reason, "candidates": candidate_values,
            "matched_customer_name": (
                names.get(customer_id)
                if customer_id is not None else None
            ),
        }
