from typing import Any

from app.workspace.constants.activity_types import ActivityType
from app.workspace.constants.project_status import ProjectStatus
from app.workspace.repositories.activity_repository import (
    ActivityRepository,
)
from app.workspace.repositories.customer_repository import (
    CustomerRepository,
)
from app.workspace.repositories.project_repository import (
    ProjectRepository,
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

        activities = (
            ActivityRepository.list_project_activities(
                project_id
            )
        )

        return {
            "customer": customer,
            "project": project,
            "followups": [],
            "open_loops": [],
            "activities": activities,
            "notes": [],
            "files": [],
        }