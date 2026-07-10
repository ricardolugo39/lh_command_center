from pprint import pprint

from app.workspace.services.project_workspace_service import (
    ProjectWorkspaceService,
)


def main() -> None:
    workspace = ProjectWorkspaceService.start_project(
        customer_name="Bavaria",
        project_name="Cambio de chumaceras",
        status="quoting",
        objective=(
            "Bavaria cambia insertos semanalmente. "
            "Queremos reemplazar la solución actual por "
            "chumaceras SKF Food Line demostrando un ROI positivo."
        ),
        proposed_solution=(
            "Chumaceras SKF Food Line, análisis de ROI "
            "y soporte técnico."
        ),
        current_blocker="Esperando cotización de SKF.",
    )

    print("\nWorkspace created successfully\n")
    pprint(workspace)


if __name__ == "__main__":
    main()
    