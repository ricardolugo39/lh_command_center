from datetime import date, datetime
from typing import Any

from app.database.transaction import transactional
from app.workspace.constants.project_status import OPEN_STATUSES
from app.workspace.repositories.followup_repository import FollowupRepository
from app.workspace.services.project_workspace_service import ProjectWorkspaceService


class OpportunityBulkUpdateService:
    MAX_SELECTION = 250

    @classmethod
    @transactional
    def apply(
        cls, *, project_ids: list[int], new_status: str = "",
        followup_date: str = "", followup_description: str = "",
        actor: str = "system",
    ) -> dict[str, int]:
        ids = list(dict.fromkeys(int(value) for value in project_ids))
        if not ids:
            raise ValueError("Seleccione al menos una oportunidad.")
        if len(ids) > cls.MAX_SELECTION:
            raise ValueError(
                f"Solo puede actualizar {cls.MAX_SELECTION} oportunidades por lote."
            )

        clean_status = str(new_status or "").strip()
        clean_date = str(followup_date or "").strip()
        clean_description = str(followup_description or "").strip()
        if not clean_status and not clean_date:
            raise ValueError("Seleccione una etapa o una fecha de próxima acción.")
        if clean_status and clean_status not in OPEN_STATUSES:
            raise ValueError(
                "El cambio masivo solo admite etapas abiertas. "
                "Las decisiones de ganar, perder o cancelar se revisan individualmente."
            )
        if clean_date:
            try:
                parsed_date = datetime.strptime(clean_date, "%Y-%m-%d").date()
            except ValueError as exc:
                raise ValueError("La fecha de próxima acción no es válida.") from exc
            if parsed_date < date.today():
                raise ValueError("La próxima acción no puede quedar en el pasado.")
            if not clean_description:
                clean_description = "Actualizar avance de la oportunidad"

        changed_statuses = created_followups = 0
        for project_id in ids:
            workspace = ProjectWorkspaceService.get_workspace(project_id)
            if workspace["project"]["status"] not in OPEN_STATUSES:
                raise ValueError(
                    f"La oportunidad {project_id} está cerrada y requiere revisión individual."
                )
            if clean_status and workspace["project"]["status"] != clean_status:
                ProjectWorkspaceService.change_status(
                    project_id=project_id,
                    new_status=clean_status,
                    created_by=actor,
                )
                changed_statuses += 1
            if clean_date and not FollowupRepository.find_pending_duplicate(
                project_id=project_id,
                due_date=clean_date,
                description=clean_description,
            ):
                FollowupRepository.create_followup(
                    project_id=project_id,
                    due_date=clean_date,
                    description=clean_description,
                    status="pending",
                    created_by=actor,
                )
                created_followups += 1

        return {
            "selected": len(ids),
            "changed_statuses": changed_statuses,
            "created_followups": created_followups,
        }
