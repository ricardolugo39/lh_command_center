from typing import Any

from app.workspace.constants.project_status import is_closed
from app.workspace.repositories.project_repository import (
    ProjectRepository,
)


class ProjectAccessPolicy:
    """Central business rule for writes to an opportunity."""

    READ_ONLY_MESSAGE = (
        "La oportunidad está cerrada y es de solo lectura."
    )

    @staticmethod
    def is_read_only(project: dict[str, Any]) -> bool:
        return is_closed(project.get("status"))

    @staticmethod
    def require_writable(project_id: int) -> dict[str, Any]:
        project = ProjectRepository.get_project(project_id)

        if project is None:
            raise ValueError(
                f"Project does not exist: {project_id}"
            )

        if ProjectAccessPolicy.is_read_only(project):
            raise ValueError(ProjectAccessPolicy.READ_ONLY_MESSAGE)

        return project
