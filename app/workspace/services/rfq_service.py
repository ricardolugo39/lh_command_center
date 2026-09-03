from typing import Any
from pathlib import Path
from sqlite3 import IntegrityError

from app.database.transaction import transactional
from app.workspace.constants.activity_types import ActivityType
from app.workspace.repositories.activity_repository import ActivityRepository
from app.workspace.repositories.contact_repository import (
    ActivityFormRepository, ContactRepository,
)
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.repositories.rfq_repository import RFQRepository
from app.workspace.repositories.customer_repository import CustomerRepository
from app.workspace.repositories.rfq_email_repository import RFQEmailRepository
from app.workspace.repositories.rfq_vendor_request_repository import (
    RFQVendorRequestRepository,
)
from app.configuration import resolve_settings


class RFQService:
    OPEN_STATUSES = {"draft", "sent", "in_progress", "answered"}
    CLOSED_STATUSES = {"closed", "cancelled"}
    OPEN_STATUS_ORDER = (
        "draft", "sent", "in_progress", "answered",
    )
    STATUS_LABELS = {
        "draft": "Borrador", "sent": "Enviado",
        "in_progress": "En gestión", "answered": "Respondido",
        "closed": "Cerrado", "cancelled": "Cancelado",
        "received": "Recibido", "analysis": "En análisis",
        "follow_up": "Seguimiento", "won": "Cerrado",
        "lost": "Perdido", "opportunity": "Oportunidad",
    }
    LEGACY_STATUS = {
        "draft": "received", "sent": "sent", "in_progress": "analysis",
        "answered": "follow_up", "closed": "won", "cancelled": "cancelled",
    }

    @staticmethod
    def default_responsible_email() -> str:
        config, _ = resolve_settings(("RFQ_DEFAULT_RESPONSIBLE_EMAIL",))
        return config.get(
            "RFQ_DEFAULT_RESPONSIBLE_EMAIL",
            "ricardo.lugo@lugohermanos.com",
        ).strip().casefold()

    @classmethod
    @transactional
    def create(cls, values: dict[str, Any]) -> int:
        clean, items = cls._validate_new(values)
        clean["rfq_number"] = RFQRepository.next_number()
        clean["status"] = "received"
        clean["workflow_status"] = "draft"
        try:
            rfq_id = RFQRepository.create(clean)
        except IntegrityError as error:
            if "prequotation_number" in str(error):
                raise ValueError(
                    "El número de precotización ya está registrado."
                ) from error
            raise
        for item in items:
            RFQRepository.add_item(rfq_id, item)
        RFQRepository.add_history(
            rfq_id, None, "draft", clean["owner_user_id"],
            "RFQ registrada",
        )
        ActivityRepository.create_activity(
            project_id=clean.get("opportunity_id"),
            customer_id=clean["customer_id"],
            contact_id=clean.get("contact_id"),
            advisor_user_id=clean["owner_user_id"],
            activity_type=ActivityType.NOTE,
            title=f"RFQ {clean['rfq_number']} creada",
            details=clean["description"],
            purpose="RFQ recibida",
            summary=clean["description"],
            created_by="system",
            occurred_at=clean["received_at"],
        )
        return rfq_id

    @classmethod
    @transactional
    def advance(
        cls, rfq_id: int, *, status: str, changed_by_user_id: int = 1,
        comment: str | None = None,
    ) -> None:
        rfq = cls.require(rfq_id)
        current = rfq.get("workflow_status") or "draft"
        if current not in cls.OPEN_STATUSES:
            raise ValueError("La RFQ ya tiene una conclusión.")
        if status not in cls.OPEN_STATUSES:
            raise ValueError("Use la conclusión para cerrar una RFQ.")
        RFQRepository.update_status(
            rfq_id, cls.LEGACY_STATUS[status], status
        )
        RFQRepository.add_history(
            rfq_id, current, status, changed_by_user_id, comment
        )

    @classmethod
    @transactional
    def conclude(
        cls, rfq_id: int, *, outcome: str, reason: str | None = None,
        final_value: Any = None, currency_code: str | None = None,
        erp_sale_reference: str | None = None,
        opportunity_id: int | None = None,
        concluded_by_user_id: int = 1,
    ) -> None:
        rfq = cls.require(rfq_id)
        current = rfq.get("workflow_status") or "draft"
        if current not in cls.OPEN_STATUSES:
            raise ValueError("La RFQ ya tiene una conclusión.")
        if outcome not in {"closed", "cancelled", "opportunity"}:
            raise ValueError("Resultado de RFQ no válido.")
        clean_reason = str(reason or "").strip() or None
        if outcome == "cancelled" and not clean_reason:
            raise ValueError("La cancelación requiere un motivo.")
        if outcome == "opportunity":
            if not opportunity_id:
                opportunity_id = cls._create_opportunity(rfq)
            project = ActivityFormRepository.get_project(opportunity_id)
            if not project or project["customer_id"] != rfq["customer_id"]:
                raise ValueError("La oportunidad no pertenece al cliente.")
        value = cls._number(final_value)
        currency = str(currency_code or "").strip().upper() or None
        if value is not None and not currency:
            raise ValueError("Indique la moneda del valor final.")
        conclusion_outcome = "opportunity" if outcome == "opportunity" else (
            "cancelled" if outcome == "cancelled" else "won"
        )
        values = {
            "outcome": conclusion_outcome, "reason": clean_reason,
            "final_value": value, "currency_code": currency,
            "erp_sale_reference": str(erp_sale_reference or "").strip() or None,
            "opportunity_id": opportunity_id,
            "concluded_by_user_id": concluded_by_user_id,
        }
        RFQRepository.conclude(rfq_id, values)
        RFQRepository.update_status(
            rfq_id,
            "opportunity" if outcome == "opportunity"
            else cls.LEGACY_STATUS[outcome],
            "closed" if outcome == "opportunity" else outcome,
            opportunity_id,
            clean_reason if outcome == "cancelled" else None,
        )
        RFQRepository.add_history(
            rfq_id, current,
            "closed" if outcome == "opportunity" else outcome,
            concluded_by_user_id,
            clean_reason or "RFQ concluida",
        )

    @classmethod
    def detail(cls, rfq_id: int) -> dict[str, Any]:
        rfq = cls.require(rfq_id)
        from app.workspace.repositories.quote_management_repository import (
            QuoteManagementRepository,
        )
        return {
            "rfq": rfq, "items": RFQRepository.list_items(rfq_id),
            "documents": RFQRepository.list_documents(rfq_id),
            "history": RFQRepository.list_history(rfq_id),
            "conclusion": RFQRepository.get_conclusion(rfq_id),
            "status_labels": cls.STATUS_LABELS,
            "open_statuses": cls.OPEN_STATUS_ORDER,
            "conclusion_labels": {
                "won": "Cerrado", "cancelled": "Cancelado",
                "opportunity": "Convertido en oportunidad",
            },
            "email_thread": RFQEmailRepository.get_thread(rfq_id),
            "email_messages": RFQEmailRepository.list_messages(rfq_id),
            "vendor_requests": RFQVendorRequestRepository.list_for_rfq(rfq_id),
            "vendor_messages": RFQVendorRequestRepository.list_messages(rfq_id),
            "vendor_attachments": RFQVendorRequestRepository.list_attachments(rfq_id),
            "related_quotes": QuoteManagementRepository.related_to_rfq(rfq_id),
        }

    @classmethod
    @transactional
    def delete_draft(cls, rfq_id: int) -> list[str]:
        rfq = cls.require(rfq_id)
        if RFQVendorRequestRepository.list_for_rfq(rfq_id):
            raise ValueError("No se puede eliminar una RFQ enviada al proveedor.")
        from app.workspace.repositories.quote_management_repository import (
            QuoteManagementRepository,
        )
        if QuoteManagementRepository.related_to_rfq(rfq_id):
            raise ValueError("No se puede eliminar una RFQ convertida en cotización.")
        paths = [
            document["stored_filename"]
            for document in RFQRepository.list_documents(rfq_id)
        ]
        RFQRepository.delete(rfq_id)
        return paths

    @staticmethod
    def remove_document_files(paths: list[str]) -> None:
        for value in paths:
            try:
                Path(value).unlink(missing_ok=True)
            except OSError:
                pass

    @classmethod
    @transactional
    def record_vendor_response(
        cls, rfq_id: int, item_id: int, values: dict[str, Any], actor_user_id: int
    ) -> None:
        items = {item["id"]: item for item in RFQRepository.list_items(rfq_id)}
        if item_id not in items:
            raise ValueError("La línea no pertenece a esta RFQ.")
        status = str(values.get("vendor_response_status") or "complete")
        if status not in {"pending", "partial", "complete", "waived"}:
            raise ValueError("Estado de respuesta no válido.")
        if status == "complete":
            for field, label in (
                ("fob_unit_usd", "FOB"), ("unit_weight_kg", "peso"),
                ("lead_time", "tiempo de entrega"),
            ):
                if not str(values.get(field) or "").strip():
                    raise ValueError(f"La respuesta completa requiere {label}.")
        RFQRepository.update_vendor_response(item_id, {**values, "vendor_response_status": status})
        current = RFQRepository.list_items(rfq_id)
        complete = sum(item["vendor_response_status"] in {"complete", "waived"} for item in current)
        workflow = "answered" if complete == len(current) else "in_progress"
        RFQRepository.update_status(rfq_id, "analysis", workflow)
        RFQRepository.add_history(
            rfq_id, cls.require(rfq_id).get("workflow_status"), workflow,
            actor_user_id, "Respuesta de proveedor actualizada",
        )

    @classmethod
    def require(cls, rfq_id: int) -> dict[str, Any]:
        rfq = RFQRepository.get(rfq_id)
        if not rfq:
            raise ValueError("La RFQ no existe.")
        return rfq

    @classmethod
    def _validate_new(
        cls, values: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        customer_id = cls._integer(values.get("customer_id"))
        new_customer_name = str(values.get("new_customer_name") or "").strip()
        if not customer_id and new_customer_name:
            if len(new_customer_name) < 2:
                raise ValueError("El nombre del cliente nuevo es demasiado corto.")
            existing = CustomerRepository.find_by_name(new_customer_name)
            customer_id = (
                existing["id"] if existing
                else CustomerRepository.create_customer(new_customer_name)
            )
        customer = ActivityFormRepository.get_customer(customer_id or 0)
        if not customer:
            raise ValueError("Seleccione un cliente válido.")
        owner = cls._integer(values.get("owner_user_id"))
        if not owner:
            default_email = cls.default_responsible_email()
            default_user = ActivityFormRepository.get_user_by_email(default_email)
            owner = cls._integer(values.get("responsible_user_id"))
            owner = owner or (default_user["id"] if default_user else None)
        if not owner:
            raise ValueError("Seleccione un responsable válido.")
        users = {user["id"] for user in ActivityFormRepository.list_users()}
        if owner not in users:
            raise ValueError("Seleccione un responsable activo.")
        sales_rep_name = str(values.get("sales_rep_name") or "").strip()
        if sales_rep_name and sales_rep_name not in ActivityFormRepository.list_sales_representatives():
            raise ValueError("Seleccione un vendedor válido de la base de ventas.")
        if not sales_rep_name:
            sales_rep_name = next(
                user["display_name"] for user in ActivityFormRepository.list_users()
                if user["id"] == owner
            )
        prequotation = str(values.get("prequotation_number") or "").strip()
        items = cls._validate_items(values.get("items") or [])
        description = str(values.get("description") or "").strip()
        if not description:
            description = ", ".join(item["reference"] for item in items)[:500]
        received_at = str(values.get("received_at") or "").strip()
        if not received_at:
            raise ValueError("La fecha recibida es obligatoria.")
        contact_id = cls._integer(values.get("contact_id"))
        if contact_id:
            contact = ContactRepository.get(contact_id)
            if not contact or contact["customer_id"] != customer_id:
                raise ValueError("El contacto no pertenece al cliente.")
        return {
            **values, "customer_id": customer_id, "contact_id": contact_id,
            "owner_user_id": owner, "description": description,
            "vendor_message": str(values.get("vendor_message") or "").strip() or None,
            "sales_rep_name": sales_rep_name,
            "received_at": received_at,
            "prequotation_number": prequotation or None,
            "prequotation_number_normalized": (
                cls._normalize_prequotation(prequotation) if prequotation else None
            ),
            "estimated_value": None, "currency_code": None,
        }, items

    @classmethod
    def _validate_items(
        cls, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not items:
            raise ValueError("Agregue al menos una referencia.")
        clean = []
        for index, item in enumerate(items, start=1):
            reference = str(item.get("reference") or "").strip()
            brand = str(item.get("brand") or "").strip()
            quantity = cls._number(item.get("quantity"))
            if not reference:
                raise ValueError(f"La referencia de la fila {index} es obligatoria.")
            if not brand:
                raise ValueError(f"La marca de la fila {index} es obligatoria.")
            if brand.casefold() in {"thk", "thomson"}:
                brand = "THK" if brand.casefold() == "thk" else "Thomson"
            if quantity is None or quantity <= 0:
                raise ValueError(
                    f"La cantidad de la fila {index} debe ser mayor que cero."
                )
            clean.append({
                "reference": reference, "brand": brand, "quantity": quantity,
                "notes": str(item.get("notes") or "").strip() or None,
                "description": reference, "display_order": index - 1,
            })
        return clean

    @staticmethod
    def _normalize_prequotation(value: str) -> str:
        return " ".join(value.strip().casefold().split())

    @staticmethod
    def _create_opportunity(rfq: dict[str, Any]) -> int:
        return ProjectRepository.create_project(
            customer_id=rfq["customer_id"],
            name=(
                "Oportunidad desde "
                f"{rfq.get('prequotation_number') or rfq['rfq_number']}"
            ),
            objective=rfq["description"],
            status="prospect",
            proposed_solution=None,
            current_blocker=None,
        )

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError) as error:
            raise ValueError("El valor monetario o cantidad no es válido.") from error
