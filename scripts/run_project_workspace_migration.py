from app.database.project_workspace_migration import (
    run_project_workspace_migration,
)


def main() -> None:
    print("Creating Project Workspace tables...")

    run_project_workspace_migration()

    print("✅ Project Workspace schema created")


if __name__ == "__main__":
    main()