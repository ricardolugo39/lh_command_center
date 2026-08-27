from app.database.migrations import upgrade


def main() -> None:
    print("Aplicando migraciones de Workspace...")
    report = upgrade()

    if report.applied_versions:
        versions = ", ".join(
            str(version) for version in report.applied_versions
        )
        print(f"✓ Migraciones aplicadas: {versions}")
    else:
        print("✓ La base de datos ya estaba actualizada")

    for warning in report.warnings:
        print(f"⚠ {warning}")

    print(f"✅ Versión de esquema: {report.current_version}")


if __name__ == "__main__":
    main()
