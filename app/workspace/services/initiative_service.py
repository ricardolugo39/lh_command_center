from typing import Any

from app.workspace.repositories.initiative_repository import (
    InitiativeRepository,
    VALID_INITIATIVE_STATUSES,
)
from app.workspace.services.quote_service import (
    QuoteService,
)

from app.workspace.repositories.project_repository import (
    ProjectRepository,
)

from app.workspace.repositories.customer_repository import (
    CustomerRepository,
)
from app.workspace.services.project_access_policy import (
    ProjectAccessPolicy,
)
from app.database.transaction import transactional


INITIATIVE_STATUS_LABELS = {
    "planning": "Planeación",
    "active": "En ejecución",
    "paused": "Pausada",
    "completed": "Finalizada",
}


class InitiativeService:

    @staticmethod
    def create_initiative(
        *,
        name: str,
        status: str,
        objective: str,
        owner: str,
        description: str | None = None,
        strategy: str | None = None,
        partner: str | None = None,
        start_date: str | None = None,
        expected_end_date: str | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        clean_name = name.strip()
        clean_status = status.strip()
        clean_objective = objective.strip()
        clean_owner = owner.strip()

        if not clean_name:
            raise ValueError(
                "El nombre de la iniciativa es obligatorio."
            )

        if clean_status not in VALID_INITIATIVE_STATUSES:
            raise ValueError(
                "El estado de la iniciativa no es válido."
            )

        if not clean_objective:
            raise ValueError(
                "El objetivo de la iniciativa es obligatorio."
            )

        if not clean_owner:
            raise ValueError(
                "El responsable de la iniciativa es obligatorio."
            )

        if (
            start_date
            and expected_end_date
            and expected_end_date < start_date
        ):
            raise ValueError(
                "La fecha fin esperada no puede ser "
                "anterior a la fecha de inicio."
            )

        initiative_id = (
            InitiativeRepository.create_initiative(
                name=clean_name,
                status=clean_status,
                objective=clean_objective,
                owner=clean_owner,
                description=description,
                strategy=strategy,
                partner=partner,
                start_date=start_date,
                expected_end_date=expected_end_date,
            )
        )

        InitiativeRepository.create_event(
            initiative_id=initiative_id,
            event_type="created",
            title="Iniciativa creada",
            details=(
                "Estado inicial: "
                f"{InitiativeService.status_label(clean_status)}"
            ),
            created_by=created_by,
        )

        return InitiativeService.get_initiative_page(
            initiative_id
        )

    @staticmethod
    def list_initiatives() -> list[dict[str, Any]]:
        initiatives = (
            InitiativeRepository.list_initiatives()
        )

        return [
            {
                **initiative,
                "status_label": (
                    InitiativeService.status_label(
                        initiative["status"]
                    )
                ),
                "display_pipeline": (
                    InitiativeService.format_cop(
                        initiative.get(
                            "pipeline_cop"
                        )
                    )
                ),
            }
            for initiative in initiatives
        ]

    @staticmethod
    def get_initiative_page(
        initiative_id: int,
    ) -> dict[str, Any]:
        initiative = (
            InitiativeRepository.get_initiative(
                initiative_id
            )
        )

        if initiative is None:
            raise ValueError(
                f"Initiative does not exist: {initiative_id}"
            )

        opportunities = (
            InitiativeRepository
            .list_related_opportunities(
                initiative_id
            )
        )

        enriched_opportunities = []

        pipeline_cop = 0.0
        active_count = 0
        won_count = 0
        lost_count = 0
        customers = set()

        for opportunity in opportunities:
            customers.add(
                opportunity["customer_name"]
            )

            status = opportunity["status"]
            is_read_only = ProjectAccessPolicy.is_read_only(
                opportunity
            )

            if status == "won":
                won_count += 1
            elif status == "lost":
                lost_count += 1
            elif not is_read_only:
                active_count += 1

                pipeline_cop += float(
                    opportunity.get(
                        "normalized_amount"
                    )
                    or 0
                )

            quote = None

            if opportunity.get("quote_number"):
                quote = QuoteService.enrich_quote(
                    {
                        "id": None,
                        "project_id": opportunity["id"],
                        "prefix": (
                            opportunity.get("prefix")
                            or "CTC"
                        ),
                        "quote_number": (
                            opportunity["quote_number"]
                        ),
                        "amount": opportunity.get(
                            "amount"
                        ),
                        "currency_code": (
                            opportunity.get(
                                "currency_code"
                            )
                            or "COP"
                        ),
                        "exchange_rate": None,
                        "exchange_rate_type": None,
                        "normalized_amount": (
                            opportunity.get(
                                "normalized_amount"
                            )
                        ),
                        "quote_date": None,
                        "quote_status": None,
                        "revision": 0,
                    }
                )

            enriched_opportunities.append(
                {
                    **opportunity,
                    "quote": quote,
                    "is_read_only": is_read_only,
                }
            )

        events = InitiativeRepository.list_events(
            initiative_id,
            limit=20,
        )

        available_opportunities = [
            project
            for project in ProjectRepository.list_unassigned_projects()
            if not ProjectAccessPolicy.is_read_only(project)
        ]

        return {
            "initiative": {
                **initiative,
                "status_label": (
                    InitiativeService.status_label(
                        initiative["status"]
                    )
                ),
            },
            "opportunities": enriched_opportunities,
            "available_opportunities": (
                available_opportunities
            ),
            "events": events,
            "summary": {
                "opportunity_count": len(
                    opportunities
                ),
                "active_count": active_count,
                "won_count": won_count,
                "lost_count": lost_count,
                "customer_count": len(customers),
                "pipeline_cop": pipeline_cop,
                "display_pipeline": (
                    InitiativeService.format_cop(
                        pipeline_cop
                    )
                ),
            },
        }

    @staticmethod
    def status_label(
        status: str,
    ) -> str:
        return INITIATIVE_STATUS_LABELS.get(
            status,
            status,
        )

    @staticmethod
    def format_cop(
        amount: float | int | None,
    ) -> str:
        return f"COP {float(amount or 0):,.0f}"

    @staticmethod
    @transactional
    def assign_opportunity(
        *,
        initiative_id: int,
        project_id: int,
        created_by: str = "system",
    ) -> dict[str, Any]:
        initiative = (
            InitiativeRepository.get_initiative(
                initiative_id
            )
        )

        if initiative is None:
            raise ValueError(
                "La iniciativa no existe."
            )

        project = ProjectAccessPolicy.require_writable(project_id)

        current_initiative_id = project.get(
            "initiative_id"
        )

        if current_initiative_id is not None:
            if current_initiative_id == initiative_id:
                return (
                    InitiativeService
                    .get_initiative_page(
                        initiative_id
                    )
                )

            raise ValueError(
                "La oportunidad ya pertenece "
                "a otra iniciativa."
            )

        customer = CustomerRepository.get_customer(
            project["customer_id"]
        )

        ProjectRepository.assign_to_initiative(
            project_id=project_id,
            initiative_id=initiative_id,
        )

        InitiativeRepository.create_event(
            initiative_id=initiative_id,
            event_type="opportunity_added",
            title="Oportunidad asociada",
            details=(
                f"{customer['name'] if customer else 'Cliente'}"
                f" · {project['name']}"
            ),
            created_by=created_by,
        )

        return (
            InitiativeService.get_initiative_page(
                initiative_id
            )
        )

    @staticmethod
    @transactional
    def remove_opportunity(
        *,
        initiative_id: int,
        project_id: int,
        created_by: str = "system",
    ) -> dict[str, Any]:
        initiative = (
            InitiativeRepository.get_initiative(
                initiative_id
            )
        )

        if initiative is None:
            raise ValueError(
                "La iniciativa no existe."
            )

        project = ProjectAccessPolicy.require_writable(project_id)

        if project.get("initiative_id") != initiative_id:
            raise ValueError(
                "La oportunidad no pertenece "
                "a esta iniciativa."
            )

        customer = CustomerRepository.get_customer(
            project["customer_id"]
        )

        ProjectRepository.remove_from_initiative(
            project_id=project_id
        )

        InitiativeRepository.create_event(
            initiative_id=initiative_id,
            event_type="opportunity_removed",
            title="Oportunidad removida",
            details=(
                f"{customer['name'] if customer else 'Cliente'}"
                f" · {project['name']}"
            ),
            created_by=created_by,
        )

        return (
            InitiativeService.get_initiative_page(
                initiative_id
            )
        )

    @staticmethod
    def delete_initiative(
        initiative_id: int,
    ) -> None:
        initiative = (
            InitiativeRepository.get_initiative(
                initiative_id
            )
        )

        if initiative is None:
            raise ValueError(
                "La iniciativa no existe."
            )

        InitiativeRepository.delete_initiative(
            initiative_id
        )

    @staticmethod
    def update_initiative(
        *,
        initiative_id: int,
        name: str,
        status: str,
        objective: str,
        owner: str,
        description: str | None = None,
        strategy: str | None = None,
        partner: str | None = None,
        start_date: str | None = None,
        expected_end_date: str | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        current = (
            InitiativeRepository.get_initiative(
                initiative_id
            )
        )

        if current is None:
            raise ValueError(
                "La iniciativa no existe."
            )

        clean_name = name.strip()
        clean_status = status.strip()
        clean_objective = objective.strip()
        clean_owner = owner.strip()

        if not clean_name:
            raise ValueError(
                "El nombre de la iniciativa es obligatorio."
            )

        if (
            clean_status
            not in VALID_INITIATIVE_STATUSES
        ):
            raise ValueError(
                "El estado de la iniciativa no es válido."
            )

        if not clean_objective:
            raise ValueError(
                "El objetivo de la iniciativa es obligatorio."
            )

        if not clean_owner:
            raise ValueError(
                "El responsable de la iniciativa es obligatorio."
            )

        if (
            start_date
            and expected_end_date
            and expected_end_date < start_date
        ):
            raise ValueError(
                "La fecha fin esperada no puede ser "
                "anterior a la fecha de inicio."
            )

        InitiativeRepository.update_initiative(
            initiative_id=initiative_id,
            name=clean_name,
            status=clean_status,
            objective=clean_objective,
            owner=clean_owner,
            description=description,
            strategy=strategy,
            partner=partner,
            start_date=start_date,
            expected_end_date=expected_end_date,
        )

        changes = []

        if current["status"] != clean_status:
            changes.append(
                "Estado: "
                f"{InitiativeService.status_label(current['status'])}"
                " → "
                f"{InitiativeService.status_label(clean_status)}"
            )

        if current["name"] != clean_name:
            changes.append(
                f"Nombre: {current['name']} → {clean_name}"
            )

        InitiativeRepository.create_event(
            initiative_id=initiative_id,
            event_type="updated",
            title="Iniciativa actualizada",
            details=(
                "\n".join(changes)
                if changes
                else "Se actualizó la información general."
            ),
            created_by=created_by,
        )

        return InitiativeService.get_initiative_page(
            initiative_id
        )

    @staticmethod
    def update_initiative(
        *,
        initiative_id: int,
        name: str,
        status: str,
        objective: str,
        owner: str,
        description: str | None = None,
        strategy: str | None = None,
        partner: str | None = None,
        start_date: str | None = None,
        expected_end_date: str | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        current = (
            InitiativeRepository.get_initiative(
                initiative_id
            )
        )

        if current is None:
            raise ValueError(
                "La iniciativa no existe."
            )

        clean_name = name.strip()
        clean_status = status.strip()
        clean_objective = objective.strip()
        clean_owner = owner.strip()

        if not clean_name:
            raise ValueError(
                "El nombre de la iniciativa es obligatorio."
            )

        if (
            clean_status
            not in VALID_INITIATIVE_STATUSES
        ):
            raise ValueError(
                "El estado de la iniciativa no es válido."
            )

        if not clean_objective:
            raise ValueError(
                "El objetivo de la iniciativa es obligatorio."
            )

        if not clean_owner:
            raise ValueError(
                "El responsable de la iniciativa es obligatorio."
            )

        if (
            start_date
            and expected_end_date
            and expected_end_date < start_date
        ):
            raise ValueError(
                "La fecha fin esperada no puede ser "
                "anterior a la fecha de inicio."
            )

        InitiativeRepository.update_initiative(
            initiative_id=initiative_id,
            name=clean_name,
            status=clean_status,
            objective=clean_objective,
            owner=clean_owner,
            description=description,
            strategy=strategy,
            partner=partner,
            start_date=start_date,
            expected_end_date=expected_end_date,
        )

        changes = []

        if current["status"] != clean_status:
            changes.append(
                "Estado: "
                f"{InitiativeService.status_label(current['status'])}"
                " → "
                f"{InitiativeService.status_label(clean_status)}"
            )

        if current["name"] != clean_name:
            changes.append(
                f"Nombre: {current['name']} → {clean_name}"
            )

        InitiativeRepository.create_event(
            initiative_id=initiative_id,
            event_type="updated",
            title="Iniciativa actualizada",
            details=(
                "\n".join(changes)
                if changes
                else "Se actualizó la información general."
            ),
            created_by=created_by,
        )

        return InitiativeService.get_initiative_page(
            initiative_id
        )
