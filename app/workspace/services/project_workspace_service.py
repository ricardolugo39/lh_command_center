from typing import Any
from datetime import datetime

from app.workspace.constants.activity_types import ActivityType
from app.workspace.constants.followup_status import FollowupStatus
from app.workspace.constants.project_status import ProjectStatus
from app.workspace.repositories.activity_repository import (
    ActivityRepository,
)
from app.workspace.repositories.customer_repository import (
    CustomerRepository,
)
from app.workspace.repositories.followup_repository import (
    FollowupRepository,
)
from app.workspace.repositories.project_repository import (
    ProjectRepository,
)
from app.workspace.repositories.customer_lookup_repository import (
    CustomerLookupRepository,
)
from app.workspace.repositories.project_brand_repository import (
    ProjectBrandRepository,
)
from app.workspace.repositories.project_quote_repository import (
    ProjectQuoteRepository,
)
from app.workspace.services.quote_service import (
    QuoteService,
)
from app.workspace.services.project_health_service import (
    ProjectHealthService,
)


class ProjectWorkspaceService:

    @staticmethod
    def start_project(
        *,
        customer_name: str,
        project_name: str,
        objective: str,
        status: str = ProjectStatus.PROSPECT,
        proposed_solution: str | None = None,
        current_blocker: str | None = None,
        erp_customer_id: str | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        customer = None

        if erp_customer_id:
            customer = CustomerRepository.find_by_erp_customer_id(
                erp_customer_id
            )

        if customer is None:
            customer_id = CustomerRepository.create_customer(
                name=customer_name,
                erp_customer_id=erp_customer_id,
            )
        else:
            customer_id = customer["id"]

        project_id = ProjectRepository.create_project(
            customer_id=customer_id,
            name=project_name,
            objective=objective,
            status=status,
            proposed_solution=proposed_solution,
            current_blocker=current_blocker,
        )

        ActivityRepository.create_activity(
            project_id=project_id,
            activity_type=ActivityType.PROJECT_CREATED,
            title="Proyecto creado",
            details=(
                f"Estado inicial: "
                f"{ProjectStatus.label(status)}"
            ),
            created_by=created_by,
        )

        return ProjectWorkspaceService.get_workspace(project_id)

    @staticmethod
    def change_status(
        *,
        project_id: int,
        new_status: str,
        created_by: str = "system",
    ) -> dict[str, Any]:
        project = ProjectRepository.get_project(project_id)

        if project is None:
            raise ValueError(
                f"Project does not exist: {project_id}"
            )

        if new_status not in ProjectStatus.LABELS:
            raise ValueError(
                f"Invalid project status: {new_status}"
            )

        old_status = project["status"]

        if old_status == new_status:
            return ProjectWorkspaceService.get_workspace(project_id)

        ProjectRepository.update_status(
            project_id=project_id,
            new_status=new_status,
        )

        ActivityRepository.create_activity(
            project_id=project_id,
            activity_type=ActivityType.STATUS_CHANGED,
            title="Estado actualizado",
            details=(
                f"{ProjectStatus.label(old_status)} "
                f"→ "
                f"{ProjectStatus.label(new_status)}"
            ),
            created_by=created_by,
        )

        return ProjectWorkspaceService.get_workspace(project_id)

    @staticmethod
    def change_blocker(
        *,
        project_id: int,
        new_blocker: str | None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        project = ProjectRepository.get_project(project_id)

        if project is None:
            raise ValueError(
                f"Project does not exist: {project_id}"
            )

        old_blocker = project["current_blocker"]

        if old_blocker == new_blocker:
            return ProjectWorkspaceService.get_workspace(project_id)

        ProjectRepository.update_blocker(
            project_id=project_id,
            blocker=new_blocker,
        )

        ActivityRepository.create_activity(
            project_id=project_id,
            activity_type=ActivityType.BLOCKER_CHANGED,
            title="Bloqueo actualizado",
            details=(
                f"{old_blocker or 'Sin bloqueo'} "
                f"→ "
                f"{new_blocker or 'Sin bloqueo'}"
            ),
            created_by=created_by,
        )

        return ProjectWorkspaceService.get_workspace(project_id)

    @staticmethod
    def create_followup(
        *,
        project_id: int,
        due_date: str,
        description: str,
        status: str = FollowupStatus.PENDING,
        created_by: str = "system",
    ) -> dict[str, Any]:
        project = ProjectRepository.get_project(project_id)

        if project is None:
            raise ValueError(
                f"Project does not exist: {project_id}"
            )

        if status not in FollowupStatus.LABELS:
            raise ValueError(
                f"Invalid follow-up status: {status}"
            )
        
        clean_description = description.strip()
        existing_followup = (
            FollowupRepository.find_pending_duplicate(
                project_id=project_id,
                due_date=due_date,
                description=clean_description,
            )
        )
        if existing_followup is not None:
            return ProjectWorkspaceService.get_workspace(project_id)

        FollowupRepository.create_followup(
            project_id=project_id,
            due_date=due_date,
            description=description,
            status=status,
            created_by=created_by,
        )

        formatted_due_date = datetime.strptime(
            due_date,
            "%Y-%m-%d",
        ).strftime("%d %b %Y")

        ActivityRepository.create_activity(
            project_id=project_id,
            activity_type=ActivityType.FOLLOWUP_CREATED,
            title="Follow-up programado",
            details=(
                f"{description}\n"
                f"Vence: {formatted_due_date}"
            ),
            created_by=created_by,
        )

        return ProjectWorkspaceService.get_workspace(project_id)

    @staticmethod
    def get_workspace(
        project_id: int,
    ) -> dict[str, Any]:
        project = ProjectRepository.get_project(project_id)

        if project is None:
            raise ValueError(
                f"Project does not exist: {project_id}"
            )

        customer = CustomerRepository.get_customer(
            project["customer_id"]
        )

        if customer is None:
            raise ValueError(
                f"Customer does not exist: "
                f"{project['customer_id']}"
            )

        activities = ActivityRepository.list_project_activities(
            project_id
        )

        followups = FollowupRepository.list_project_followups(
            project_id
        )

        quotes = QuoteService.list_project_quotes(
            project_id
        )

        brands = (
            ProjectBrandRepository.list_project_brands(
                project_id
            )
        )

        customer_site = None

        if project.get("customer_site_id"):
            customer_site = (
                CustomerLookupRepository.get_customer_site(
                    project["customer_site_id"]
                )
            )

        # quotes = ProjectQuoteRepository.list_project_quotes(
        #     project_id
        # )

        brands = ProjectBrandRepository.list_project_brands(
            project_id
        )

        workspace = {
            "customer": customer,
            "customer_site": customer_site,
            "project": project,
            "quotes": quotes,
            "brands": brands,
            "followups": followups,
            "open_loops": [],
            "activities": activities,
            "notes": [],
            "files": [],
        }

        workspace["health"] = (
            ProjectHealthService.calculate(
                workspace
            )
        )

        return workspace
    
    @staticmethod
    def complete_followup(
        *,
        followup_id: int,
        created_by: str = "system",
    ) -> dict[str, Any]:

        followup = FollowupRepository.get_followup(
            followup_id
        )

        if followup is None:
            raise ValueError(
                f"Follow-up does not exist: {followup_id}"
            )

        if followup["status"] == FollowupStatus.COMPLETED:
            return ProjectWorkspaceService.get_workspace(
                followup["project_id"]
            )

        FollowupRepository.complete_followup(
            followup_id
        )

        ActivityRepository.create_activity(
            project_id=followup["project_id"],
            activity_type=ActivityType.FOLLOWUP_COMPLETED,
            title="Follow-up completado",
            details=followup["description"],
            created_by=created_by,
        )

        return ProjectWorkspaceService.get_workspace(
            followup["project_id"]
        )
    @staticmethod
    def create_project_mvp(
        *,
        erp_customer_id: str,
        customer_site_id: str,
        project_name: str,
        objective: str,
        sales_rep: str,
        status: str = ProjectStatus.PROSPECT,
        proposed_solution: str | None = None,
        current_blocker: str | None = None,
        brands: list[str] | None = None,
        quote_prefix: str | None = None,
        quote_number: str | None = None,
        quote_date: str | None = None,
        quote_amount: float | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        clean_customer_id = erp_customer_id.strip()
        clean_site_id = customer_site_id.strip()
        clean_project_name = project_name.strip()
        clean_objective = objective.strip()
        clean_sales_rep = sales_rep.strip()

        if not clean_customer_id:
            raise ValueError(
                "Debe seleccionar un cliente."
            )

        if not clean_site_id:
            raise ValueError(
                "Debe seleccionar una sede."
            )

        if not clean_project_name:
            raise ValueError(
                "El nombre del proyecto es obligatorio."
            )

        if not clean_objective:
            raise ValueError(
                "El objetivo del proyecto es obligatorio."
            )

        if not clean_sales_rep:
            raise ValueError(
                "El vendedor es obligatorio."
            )

        if status not in ProjectStatus.LABELS:
            raise ValueError(
                f"Estado inválido: {status}"
            )

        customer_site = (
            CustomerLookupRepository.get_customer_site(
                clean_site_id
            )
        )

        if customer_site is None:
            raise ValueError(
                "La sede seleccionada no existe."
            )

        if (
            str(customer_site["customer_id"])
            != clean_customer_id
        ):
            raise ValueError(
                "El cliente y la sede seleccionados no coinciden."
            )

        customer = (
            CustomerRepository.find_by_erp_customer_id(
                clean_customer_id
            )
        )

        if customer is None:
            internal_customer_id = (
                CustomerRepository.create_customer(
                    name=customer_site["customer_name"],
                    erp_customer_id=clean_customer_id,
                )
            )
        else:
            internal_customer_id = customer["id"]

        project_id = ProjectRepository.create_project(
            customer_id=internal_customer_id,
            customer_site_id=clean_site_id,
            sales_rep=clean_sales_rep,
            name=clean_project_name,
            objective=clean_objective,
            status=status,
            proposed_solution=proposed_solution,
            current_blocker=current_blocker,
        )

        for brand in brands or []:
            ProjectBrandRepository.add_brand(
                project_id=project_id,
                brand=brand,
            )

        if quote_number and quote_number.strip():
            ProjectQuoteRepository.attach_quote(
                project_id=project_id,
                prefix=quote_prefix or "CTC",
                quote_number=quote_number,
                quote_date=quote_date,
                amount=quote_amount,
            )

        ActivityRepository.create_activity(
            project_id=project_id,
            activity_type=ActivityType.PROJECT_CREATED,
            title="Proyecto creado",
            details=(
                f"Estado inicial: "
                f"{ProjectStatus.label(status)}"
            ),
            created_by=created_by,
        )

        return ProjectWorkspaceService.get_workspace(
            project_id
        )

    @staticmethod
    def add_activity(
        *,
        project_id: int,
        activity_type: str,
        details: str,
        followup_due_date: str | None = None,
        followup_description: str | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        project = ProjectRepository.get_project(project_id)

        if project is None:
            raise ValueError(
                f"Project does not exist: {project_id}"
            )

        clean_activity_type = activity_type.strip()
        clean_details = details.strip()

        if not ActivityType.is_manual_type(
            clean_activity_type
        ):
            raise ValueError(
                f"Invalid manual activity type: "
                f"{clean_activity_type}"
            )

        if len(clean_details) < 3:
            raise ValueError(
                "La actividad debe tener al menos "
                "3 caracteres."
            )

        ActivityRepository.create_activity(
            project_id=project_id,
            activity_type=clean_activity_type,
            title=ActivityType.label(
                clean_activity_type
            ),
            details=clean_details,
            created_by=created_by,
        )

        if followup_due_date:

            description = (
                followup_description.strip()
                if followup_description
                else "Follow up"
            )

            FollowupRepository.create_followup(
                project_id=project_id,
                due_date=followup_due_date,
                description=description,
                status=FollowupStatus.PENDING,
                created_by=created_by,
            )

            formatted_due_date = datetime.strptime(
                followup_due_date,
                "%Y-%m-%d",
            ).strftime("%d %b %Y")

            ActivityRepository.create_activity(
                project_id=project_id,
                activity_type=ActivityType.FOLLOWUP_CREATED,
                title="Follow-up programado",
                details=(
                    f"{description}\n"
                    f"Vence: {formatted_due_date}"
                ),
                created_by=created_by,
            )

        return ProjectWorkspaceService.get_workspace(
            project_id
        )
    
    @staticmethod
    def update_project_details(
        *,
        project_id: int,
        project_name: str,
        objective: str,
        proposed_solution: str | None,
        current_blocker: str | None,
        sales_rep: str,
        brands: list[str] | None = None,
        quote_prefix: str = "CTC",
        quote_number: str | None = None,
        quote_date: str | None = None,
        quote_amount: float | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        project = ProjectRepository.get_project(project_id)

        if project is None:
            raise ValueError(
                f"Project does not exist: {project_id}"
            )

        clean_name = project_name.strip()
        clean_objective = objective.strip()
        clean_sales_rep = sales_rep.strip()

        if not clean_name:
            raise ValueError(
                "El nombre del proyecto es obligatorio."
            )

        if not clean_objective:
            raise ValueError(
                "El objetivo del proyecto es obligatorio."
            )

        if not clean_sales_rep:
            raise ValueError(
                "El vendedor es obligatorio."
            )

        ProjectRepository.update_project(
            project_id=project_id,
            name=clean_name,
            status=project["status"],
            objective=clean_objective,
            proposed_solution=proposed_solution,
            current_blocker=current_blocker,
            sales_rep=clean_sales_rep,
        )

        ProjectBrandRepository.replace_project_brands(
            project_id=project_id,
            brands=brands or [],
        )

        ProjectQuoteRepository.replace_primary_quote(
            project_id=project_id,
            prefix=quote_prefix,
            quote_number=quote_number,
            quote_date=quote_date,
            amount=quote_amount,
        )

        ActivityRepository.create_activity(
            project_id=project_id,
            activity_type=ActivityType.NOTE,
            title="Proyecto actualizado",
            details="Se actualizaron los datos generales del proyecto.",
            created_by=created_by,
        )

        return ProjectWorkspaceService.get_workspace(
            project_id
        )
    @staticmethod
    def reschedule_followup(
        *,
        followup_id: int,
        due_date: str,
        created_by: str = "system",
    ) -> dict[str, Any]:

        followup = FollowupRepository.get_followup(
            followup_id
        )

        if followup is None:
            raise ValueError(
                f"Follow-up does not exist: {followup_id}"
            )

        old_due_date = followup["due_date"]

        if old_due_date == due_date:
            return ProjectWorkspaceService.get_workspace(
                followup["project_id"]
            )

        FollowupRepository.reschedule_followup(
            followup_id=followup_id,
            due_date=due_date,
        )

        ActivityRepository.create_activity(
            project_id=followup["project_id"],
            activity_type=ActivityType.FOLLOWUP_RESCHEDULED,
            title="Follow-up reprogramado",
            details=(
                f"{old_due_date} → {due_date}"
            ),
            created_by=created_by,
        )

        return ProjectWorkspaceService.get_workspace(
            followup["project_id"]
        )
    
    @staticmethod
    def delete_project(
        project_id: int,
    ) -> None:
        project = ProjectRepository.get_project(
            project_id
        )

        if project is None:
            raise ValueError(
                "La oportunidad no existe."
            )

        ProjectRepository.delete_project(
            project_id
        )