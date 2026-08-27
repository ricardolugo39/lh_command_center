import argparse

from app.workspace.services.commercial_visit_service import CommercialVisitService


def main():
    parser=argparse.ArgumentParser(description="Sincroniza visitas comerciales desde Google Sheets.")
    parser.add_argument("--rebuild",action="store_true",
                        help="Reconstruye exclusivamente las visitas importadas desde AppSheet.")
    parser.add_argument("--confirm",action="store_true",
                        help="Confirma la eliminación previa requerida por --rebuild.")
    args=parser.parse_args()
    if args.rebuild and not args.confirm:
        parser.error("--rebuild requiere --confirm")
    result=(CommercialVisitService.rebuild_configured_source()
            if args.rebuild else CommercialVisitService.sync_configured_source())
    print(
        "Sincronización completada: "
        f"{result['inserted']} nuevas, {result['updated']} actualizadas, "
        f"{result['unchanged']} sin cambios, {result['errors']} errores."
    )


if __name__ == "__main__":
    main()
