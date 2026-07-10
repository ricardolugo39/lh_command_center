from pprint import pprint

from app.workspace.constants.project_status import ProjectStatus
from app.workspace.services.project_workspace_service import ProjectWorkspaceService


def main():

    ProjectWorkspaceService.change_status(
        project_id=4,
        new_status=ProjectStatus.NEGOTIATION,
    )

    workspace = ProjectWorkspaceService.get_workspace(4)

    pprint(workspace)


if __name__ == "__main__":
    main()