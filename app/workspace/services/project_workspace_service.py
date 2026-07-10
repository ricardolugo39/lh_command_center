from typing import Any

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
        status: str = "prospect",
        proposed_solution: str | None = None,
        current_blocker: str | None = None,
        erp_customer_id: str | None = None,
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

        return ProjectWorkspaceService.get_workspace(project_id)

    @staticmethod
    def get_workspace(project_id: int) -> dict[str, Any]:
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

        return {
            "customer": customer,
            "project": project,
            "followups": [],
            "open_loops": [],
            "activities": [],
            "notes": [],
            "files": [],
        }