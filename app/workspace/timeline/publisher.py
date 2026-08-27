from decimal import Decimal

from app.workspace.constants.activity_types import ActivityType
from app.workspace.repositories.activity_repository import ActivityRepository


class OpportunityTimelinePublisher:
    APPROVAL_EVENTS = {
        "created": (
            ActivityType.APPROVAL_CREATED,
            "Solicitud de aprobación comercial creada",
        ),
        "submitted": (
            ActivityType.APPROVAL_SUBMITTED,
            "Aprobación comercial enviada",
        ),
        "approved": (
            ActivityType.APPROVAL_APPROVED,
            "Descuento comercial aprobado",
        ),
        "returned": (
            ActivityType.APPROVAL_RETURNED,
            "Aprobación comercial devuelta",
        ),
        "rejected": (
            ActivityType.APPROVAL_REJECTED,
            "Aprobación comercial rechazada",
        ),
        "cancelled": (
            ActivityType.APPROVAL_CANCELLED,
            "Solicitud de aprobación cancelada",
        ),
    }

    @classmethod
    def publish_approval_event(
        cls,
        *,
        event: str,
        approval: dict,
        actor: str,
        comments: str = "",
        monetary: dict | None = None,
        previous_amount=None,
    ) -> int:
        activity_type, title = cls.APPROVAL_EVENTS[event]
        number = f"AP-{int(approval['id']):06d}"
        details = cls._approval_details(
            event, approval, number, actor, comments, monetary, previous_amount
        )
        return ActivityRepository.create_activity(
            project_id=approval["project_id"],
            activity_type=activity_type,
            title=title,
            details=details,
            created_by=actor,
        )

    @staticmethod
    def publish_visit_event(
        *, visit_id: int, project_id: int, visit: dict
    ) -> int:
        title = {
            "Comercial": "Visita comercial",
            "Técnica": "Visita técnica",
            "Seguimiento": "Visita de seguimiento",
            "Postventa": "Visita postventa",
        }.get(visit.get("visit_type"), "Visita comercial")
        details = (
            f"{visit.get('advisor_name') or 'Asesor sin identificar'} realizó una visita.\n"
            f"Contacto: {visit.get('visited_contact_name') or 'Sin registro'}"
            f"{(' · ' + visit['visited_contact_role']) if visit.get('visited_contact_role') else ''}\n"
            f"Motivo: {visit.get('visit_reason') or 'Sin registro'}\n"
            f"Necesidad detectada: {visit.get('detected_need') or 'Sin registro'}\n"
            f"Próxima acción: {visit.get('required_action') or 'Sin acción registrada'}\n"
            f"[visita:{visit_id}]"
        )
        return ActivityRepository.create_activity(
            project_id,
            ActivityType.VISIT,
            title,
            details,
            visit.get("advisor_name") or "AppSheet",
            occurred_at=visit.get("visit_date"),
        )

    @classmethod
    def _approval_details(
        cls, event, approval, number, actor, comments, monetary, previous_amount
    ):
        requested = cls._percent(approval.get("requested_discount"))
        product = (
            approval.get("product_reference")
            or approval.get("product")
            or "producto sin referencia"
        )
        if event == "created":
            return (
                f"Se creó la solicitud {number} por un descuento del "
                f"{requested} para {product}.\nTipo: Descuento comercial\n"
                f"Solicitante: {actor}"
            )
        if event == "submitted":
            values = monetary or {}
            return (
                f"Se envió la solicitud {number} para aprobación.\n"
                f"Descuento solicitado: {requested}\n"
                f"Precio solicitado: {cls._money(values.get('approved_unit_price'), approval.get('currency'))}\n"
                f"Monto solicitado: {cls._money(values.get('approved_total_amount'), approval.get('currency'))}"
            )
        if event == "approved":
            old = (
                cls._money(previous_amount, approval.get("currency"))
                if previous_amount is not None
                else "Sin monto registrado"
            )
            return (
                f"Se aprobó la solicitud {number} con un descuento del "
                f"{cls._percent(monetary['approved_discount_percent'])}.\n"
                f"Descuento solicitado: {requested}\n"
                f"Precio de lista: {cls._money(monetary['list_unit_price'], monetary['currency'])}\n"
                f"Precio final aprobado: {cls._money(monetary['approved_unit_price'], monetary['currency'])}\n"
                f"Cantidad: {monetary['quantity']}\n"
                f"Monto anterior: {old}\n"
                f"Nuevo monto: {cls._money(monetary['approved_total_amount'], monetary['currency'])}\n"
                f"Aprobado por: {actor}\nComentarios: {comments}"
            )
        label = {
            "returned": "devuelta",
            "rejected": "rechazada",
            "cancelled": "cancelada",
        }[event]
        return (
            f"La solicitud {number} fue {label}.\n"
            f"Descuento solicitado: {requested}\nUsuario: {actor}\n"
            f"Comentarios: {comments or 'Sin comentarios'}"
        )

    @staticmethod
    def _percent(value) -> str:
        return (
            f"{Decimal(str(value or 0)).quantize(Decimal('0.01'))}%"
            .replace(".", ",")
        )

    @staticmethod
    def _money(value, currency) -> str:
        if value in (None, ""):
            return "No disponible"
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
        return f"{currency or 'COP'} {amount:,.2f}"
