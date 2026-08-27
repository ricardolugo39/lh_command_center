from typing import Any

from app.workspace.constants.activity_types import ActivityType
from app.workspace.repositories.activity_repository import (
    ActivityRepository,
)
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.repositories.followup_repository import FollowupRepository
from app.workspace.services.project_access_policy import ProjectAccessPolicy
from app.workspace.services.project_workspace_service import (
    ProjectWorkspaceService,
)
from app.database.transaction import transactional


class ProjectClosureService:
    LOST_REASONS = {
        "price",
        "delivery",
        "inventory",
        "technical_specification",
        "customer_cancelled",
        "no_budget",
        "commercial_relationship",
        "other",
    }

    RESULT_CHANGERS = {
        "better_price",
        "greater_availability",
        "special_skf_discount",
        "engineering_support",
        "technical_visit",
        "training",
        "immediate_delivery",
        "other",
    }

    @staticmethod
    @transactional
    def close_as_won(
        *,
        project_id: int,
        won_amount: float,
        customer_po: str | None = None,
        order_number: str | None = None,
        comments: str | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        ProjectAccessPolicy.require_writable(
            project_id
        )

        try:
            clean_amount = float(won_amount)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "El valor final de venta no es válido."
            ) from exc

        if clean_amount <= 0:
            raise ValueError(
                "El valor final de venta debe ser mayor que cero."
            )

        clean_customer_po = (
            customer_po.strip()
            if customer_po
            else None
        )

        clean_order_number = (
            order_number.strip()
            if order_number
            else None
        )

        clean_comments = (
            comments.strip()
            if comments
            else None
        )

        ProjectRepository.close_as_won(
            project_id=project_id,
            won_amount=clean_amount,
            customer_po=clean_customer_po,
            order_number=clean_order_number,
            comments=clean_comments,
        )
        completed_followups = FollowupRepository.complete_pending_for_project(project_id)

        details = [
            "Resultado: Ganada",
            f"Valor final de venta: {clean_amount:,.2f}",
        ]

        if clean_customer_po:
            details.append(
                f"Orden de compra del cliente: {clean_customer_po}"
            )

        if clean_order_number:
            details.append(
                f"Número de pedido: {clean_order_number}"
            )

        if clean_comments:
            details.append(
                f"Comentarios: {clean_comments}"
            )
        if completed_followups:
            details.append(f"Seguimientos cerrados automáticamente: {completed_followups}")

        ActivityRepository.create_activity(
            project_id=project_id,
            activity_type=ActivityType.OPPORTUNITY_CLOSED,
            title="Oportunidad cerrada como ganada",
            details="\n".join(details),
            created_by=created_by,
        )

        return ProjectWorkspaceService.get_workspace(
            project_id
        )

    @staticmethod
    @transactional
    def close_as_lost(
        *,
        project_id: int,
        lost_reason: str,
        result_changer: str | None = None,
        competitor_company: str | None = None,
        competitor_type: str | None = None,
        competitor_brand: str | None = None,
        comments: str | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        ProjectAccessPolicy.require_writable(
            project_id
        )

        clean_reason = lost_reason.strip().lower()

        if clean_reason not in (
            ProjectClosureService.LOST_REASONS
        ):
            raise ValueError(
                "El motivo de pérdida no es válido."
            )

        clean_result_changer = (
            result_changer.strip().lower()
            if result_changer
            else None
        )

        if (
            clean_result_changer
            and clean_result_changer
            not in ProjectClosureService.RESULT_CHANGERS
        ):
            raise ValueError(
                "La acción que habría cambiado el resultado no es válida."
            )

        clean_company = (
            competitor_company.strip()
            if competitor_company
            else None
        )

        clean_type = (
            competitor_type.strip()
            if competitor_type
            else None
        )

        clean_brand = (
            competitor_brand.strip()
            if competitor_brand
            else None
        )

        clean_comments = (
            comments.strip()
            if comments
            else None
        )

        ProjectRepository.close_as_lost(
            project_id=project_id,
            lost_reason=clean_reason,
            result_changer=clean_result_changer,
            competitor_company=clean_company,
            competitor_type=clean_type,
            competitor_brand=clean_brand,
            comments=clean_comments,
        )
        completed_followups = FollowupRepository.complete_pending_for_project(project_id)

        details = [
            "Resultado: Perdida",
            (
                "Motivo principal: "
                f"{clean_reason.replace('_', ' ').title()}"
            ),
        ]

        if clean_result_changer:
            details.append(
                "Qué habría cambiado el resultado: "
                f"{clean_result_changer.replace('_', ' ').title()}"
            )

        if clean_company:
            details.append(
                f"Empresa competidora: {clean_company}"
            )

        if clean_type:
            details.append(
                f"Tipo de competidor: {clean_type}"
            )

        if clean_brand:
            details.append(
                f"Marca competidora: {clean_brand}"
            )

        if clean_comments:
            details.append(
                f"Comentarios: {clean_comments}"
            )
        if completed_followups:
            details.append(f"Seguimientos cerrados automáticamente: {completed_followups}")

        ActivityRepository.create_activity(
            project_id=project_id,
            activity_type=ActivityType.OPPORTUNITY_CLOSED,
            title="Oportunidad cerrada como perdida",
            details="\n".join(details),
            created_by=created_by,
        )

        return ProjectWorkspaceService.get_workspace(
            project_id
        )

    @staticmethod
    @transactional
    def cancel(
        *,
        project_id: int,
        reason: str,
        comments: str | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        ProjectAccessPolicy.require_writable(
            project_id
        )

        clean_reason = reason.strip()

        if not clean_reason:
            raise ValueError(
                "El motivo de cancelación es obligatorio."
            )

        clean_comments = (
            comments.strip()
            if comments
            else None
        )

        ProjectRepository.cancel_project(
            project_id=project_id,
            reason=clean_reason,
            comments=clean_comments,
        )
        completed_followups = FollowupRepository.complete_pending_for_project(project_id)

        details = [
            "Resultado: Cancelada",
            f"Motivo: {clean_reason}",
        ]

        if clean_comments:
            details.append(
                f"Comentarios: {clean_comments}"
            )
        if completed_followups:
            details.append(f"Seguimientos cerrados automáticamente: {completed_followups}")

        ActivityRepository.create_activity(
            project_id=project_id,
            activity_type=ActivityType.OPPORTUNITY_CLOSED,
            title="Oportunidad cancelada",
            details="\n".join(details),
            created_by=created_by,
        )

        return ProjectWorkspaceService.get_workspace(
            project_id
        )

    @staticmethod
    @transactional
    def reopen(*, project_id: int, created_by: str = "system") -> dict[str, Any]:
        project = ProjectRepository.get_project(project_id)
        if project is None:
            raise ValueError("La oportunidad no existe.")
        if project.get("status") not in {"won", "lost", "cancelled"}:
            raise ValueError("La oportunidad ya está abierta.")
        previous_status = project["status"]
        ProjectRepository.reopen_project(project_id)
        ActivityRepository.create_activity(
            project_id=project_id,
            activity_type=ActivityType.STATUS_CHANGED,
            title="Oportunidad reabierta",
            details=f"Estado anterior: {previous_status}. Nuevo estado: Negociación.",
            created_by=created_by,
        )
        return ProjectWorkspaceService.get_workspace(project_id)
