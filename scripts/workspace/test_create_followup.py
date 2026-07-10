from pprint import pprint

from app.workspace.constants.followup_status import (
    FollowupStatus,
)
from app.workspace.services.project_workspace_service import (
    ProjectWorkspaceService,
)


def main():

    workspace = ProjectWorkspaceService.create_followup(
        project_id=4,
        due_date="2026-07-15",
        description="Llamar al comprador.",
        status=FollowupStatus.PENDING,
    )

    pprint(workspace)


if __name__ == "__main__":
    main()