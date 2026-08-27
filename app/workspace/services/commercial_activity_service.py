from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.database.transaction import transaction
from app.storage import upload_path
from app.workspace.constants.activity_types import ActivityType
from app.workspace.repositories.activity_repository import ActivityRepository
from app.workspace.repositories.contact_repository import (
    ActivityFormRepository,
    ContactRepository,
)


@dataclass(frozen=True)
class ActivityCreationResult:
    activity_id: int
    customer_id: int
    project_id: int | None


class CommercialActivityService:
    EVIDENCE_ROOT = upload_path("activity-evidence")
    RESULT_TYPES = {
        "opportunity_identified", "rfq_received", "quote_requested",
        "training_completed", "support_completed", "followup_required",
        "no_customer_need", "pending_information", "other",
    }

    @classmethod
    def form_context(cls, customer_id: int) -> dict[str, Any]:
        customer = ActivityFormRepository.get_customer(customer_id)
        if not customer:
            raise ValueError("El cliente no existe.")
        return {
            "customer": customer,
            "contacts": ContactRepository.list_for_customer(customer_id),
            "projects": ActivityFormRepository.list_projects(customer_id),
            "agreements": ActivityFormRepository.list_agreements(customer_id),
            "users": ActivityFormRepository.list_users(),
            "activity_types": [
                (value, ActivityType.label(value))
                for value in sorted(ActivityType.MANUAL_TYPES)
            ],
        }

    @classmethod
    def create(
        cls, *, values: dict[str, Any], evidence_files: list[FileStorage]
    ) -> ActivityCreationResult:
        clean = cls._validate(values)
        stored_files: list[Path] = []
        try:
            with transaction():
                activity_id = ActivityRepository.create_activity(
                    project_id=clean.get("project_id"),
                    customer_id=clean["customer_id"],
                    contact_id=clean.get("contact_id"),
                    advisor_user_id=clean.get("advisor_user_id"),
                    activity_type=clean["activity_type"],
                    title=clean["purpose"],
                    details=clean["summary"],
                    purpose=clean["purpose"],
                    summary=clean["summary"],
                    identified_need=clean.get("identified_need"),
                    identified_risk=clean.get("identified_risk"),
                    supplier_participated=clean["supplier_participated"],
                    supplier_name=clean.get("supplier_name"),
                    supplier_person_name=clean.get("supplier_person_name"),
                    supplier_person_role=clean.get("supplier_person_role"),
                    supplier_objective=clean.get("supplier_objective"),
                    agreement_id=clean.get("agreement_id"),
                    potential_value=clean.get("potential_value"),
                    currency_code=clean.get("currency_code"),
                    city=clean.get("city"),
                    site_name=clean.get("site_name"),
                    visited_area=clean.get("visited_area"),
                    created_by=clean.get("created_by", "system"),
                    occurred_at=clean["occurred_at"],
                )
                ActivityRepository.add_participants(
                    activity_id, clean["participant_user_ids"]
                )
                ActivityRepository.add_results(activity_id, clean["results"])
                for order, upload in enumerate(evidence_files):
                    if not upload or not upload.filename:
                        continue
                    metadata, stored = cls._store_evidence(activity_id, upload)
                    stored_files.append(stored)
                    ActivityRepository.add_evidence(
                        activity_id, {**metadata, "display_order": order}
                    )
                ActivityRepository.add_history(
                    activity_id, "created",
                    json.dumps(clean, ensure_ascii=False, default=str),
                    clean.get("advisor_user_id"),
                )
            return ActivityCreationResult(
                activity_id, clean["customer_id"], clean.get("project_id")
            )
        except Exception:
            for stored in stored_files:
                stored.unlink(missing_ok=True)
            raise

    @classmethod
    def create_contact(cls, values: dict[str, Any]) -> int:
        customer_id = cls._integer(values.get("customer_id"))
        full_name = str(values.get("full_name") or "").strip()
        if not customer_id or not ActivityFormRepository.get_customer(customer_id):
            raise ValueError("Seleccione un cliente válido.")
        if not full_name:
            raise ValueError("El nombre del contacto es obligatorio.")
        with transaction():
            return ContactRepository.create({
                **values, "customer_id": customer_id, "full_name": full_name,
            })

    @classmethod
    def _validate(cls, values: dict[str, Any]) -> dict[str, Any]:
        customer_id = cls._integer(values.get("customer_id"))
        if not customer_id or not ActivityFormRepository.get_customer(customer_id):
            raise ValueError("Seleccione un cliente válido.")
        activity_type = str(values.get("activity_type") or "").strip()
        if not ActivityType.is_manual_type(activity_type):
            raise ValueError("Seleccione un tipo de actividad válido.")
        purpose = str(values.get("purpose") or "").strip()
        summary = str(values.get("summary") or "").strip()
        occurred_at = str(values.get("occurred_at") or "").strip()
        if not purpose or not summary or not occurred_at:
            raise ValueError("Fecha, motivo y resumen son obligatorios.")

        project_id = cls._integer(values.get("project_id"))
        if project_id:
            project = ActivityFormRepository.get_project(project_id)
            if not project or project["customer_id"] != customer_id:
                raise ValueError("La oportunidad no pertenece al cliente.")
        contact_id = cls._integer(values.get("contact_id"))
        if contact_id:
            contact = ContactRepository.get(contact_id)
            if not contact or contact["customer_id"] != customer_id:
                raise ValueError("El contacto no pertenece al cliente.")
        agreement_id = cls._integer(values.get("agreement_id"))
        if agreement_id:
            agreement = ActivityFormRepository.get_agreement(agreement_id)
            if not agreement or agreement["customer_id"] != customer_id:
                raise ValueError("El acuerdo no pertenece al cliente.")

        supplier_participated = bool(values.get("supplier_participated"))
        supplier_name = str(values.get("supplier_name") or "").strip() or None
        if supplier_participated and not supplier_name:
            raise ValueError(
                "El proveedor es obligatorio cuando participó en la actividad."
            )
        potential = values.get("potential_value")
        potential_value = float(potential) if str(potential or "").strip() else None
        currency = str(values.get("currency_code") or "").strip().upper() or None
        if potential_value is not None and not currency:
            raise ValueError("Indique la moneda del valor potencial.")
        results = list(dict.fromkeys(values.get("results") or []))
        if any(result not in cls.RESULT_TYPES for result in results):
            raise ValueError("La actividad contiene un resultado no válido.")
        participants = [
            value for value in (
                cls._integer(item) for item in values.get("participant_user_ids", [])
            ) if value
        ]
        return {
            **values, "customer_id": customer_id, "project_id": project_id,
            "contact_id": contact_id, "agreement_id": agreement_id,
            "advisor_user_id": cls._integer(values.get("advisor_user_id")),
            "activity_type": activity_type, "purpose": purpose,
            "summary": summary, "occurred_at": occurred_at,
            "supplier_participated": supplier_participated,
            "supplier_name": supplier_name, "potential_value": potential_value,
            "currency_code": currency, "results": results,
            "participant_user_ids": participants,
        }

    @classmethod
    def _store_evidence(
        cls, activity_id: int, upload: FileStorage
    ) -> tuple[dict[str, Any], Path]:
        filename = secure_filename(upload.filename or "evidencia")
        content = upload.read()
        digest = hashlib.sha256(content).hexdigest()
        folder = cls.EVIDENCE_ROOT / str(activity_id)
        folder.mkdir(parents=True, exist_ok=True)
        stored = folder / f"{digest}-{filename}"
        stored.write_bytes(content)
        return {
            "original_filename": upload.filename,
            "stored_filename": str(stored),
            "mime_type": upload.mimetype or "application/octet-stream",
            "size_bytes": len(content),
            "description": None,
        }, stored

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None
