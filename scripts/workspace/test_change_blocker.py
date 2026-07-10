from pprint import pprint

from app.workspace.services.project_workspace_service import (
    ProjectWorkspaceService,
)


def main():

    workspace = ProjectWorkspaceService.change_blocker(
        project_id=4,
        new_blocker="Esperando aprobación del cliente.",
    )

    pprint(workspace)


if __name__ == "__main__":
    main()