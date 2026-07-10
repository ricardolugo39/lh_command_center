from pprint import pprint

from app.workspace.services.project_workspace_service import (
    ProjectWorkspaceService,
)


def main():

    workspace = ProjectWorkspaceService.complete_followup(
        followup_id=1,
    )

    pprint(workspace)


if __name__ == "__main__":
    main()