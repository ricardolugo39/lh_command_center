from app.database.migrations import upgrade


def main() -> None:
    print("Creating Workspace tables...")
    upgrade()
    print("✅ Workspace tables created")


if __name__ == "__main__":
    main()