from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from app.database.transaction import transactional
from app.workspace.repositories.initiative_campaign_repository import (
    InitiativeCampaignRepository,
)
from app.workspace.repositories.initiative_repository import InitiativeRepository


TRACKING_HEADERS = [
    "_ID", "Cliente", "Ciudad", "Prioridad", "Estado", "Fecha de contacto",
    "Contacto en cliente", "Aplicación o máquina", "Marca o referencia instalada",
    "Interés", "Próxima acción", "Fecha compromiso", "¿Oportunidad?",
]


class InitiativeCampaignService:

    @staticmethod
    def get_campaign(initiative_id: int) -> dict[str, Any]:
        customers = InitiativeCampaignRepository.list_customers(initiative_id)
        total = len(customers)
        contacted = sum(c["status"] not in {"Pendiente", "Contacto intentado"} for c in customers)
        applications = sum(bool(c.get("application")) for c in customers)
        opportunities = sum(c.get("opportunity_decision") == "Sí" for c in customers)
        return {
            "customers": customers,
            "summary": {
                "assigned": total,
                "contacted": contacted,
                "contacted_pct": round(contacted * 100 / total) if total else 0,
                "applications": applications,
                "applications_pct": round(applications * 100 / total) if total else 0,
                "opportunities": opportunities,
                "opportunities_pct": round(opportunities * 100 / total) if total else 0,
            },
        }

    @staticmethod
    def export_workbook(initiative_id: int, advisor: str | None = None) -> tuple[BytesIO, str]:
        initiative = InitiativeRepository.get_initiative(initiative_id)
        if not initiative:
            raise ValueError("La iniciativa no existe.")
        customers = InitiativeCampaignRepository.list_customers(initiative_id)
        if advisor:
            customers = [item for item in customers if item["advisor"] == advisor]
        if not customers:
            raise ValueError("No hay clientes de campaña para exportar.")

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Seguimiento"
        sheet.append([initiative["name"]])
        sheet.append(["Actualice las columnas azules. El Command Center usa el ID para sincronizar cada cliente."])
        sheet.append(TRACKING_HEADERS)
        for customer in customers:
            sheet.append([
                customer["source_key"], customer["customer_name"], customer.get("city"),
                customer.get("priority"), customer.get("status"), customer.get("contact_date"),
                customer.get("contact_name"), customer.get("application"),
                customer.get("installed_reference"), customer.get("interest"),
                customer.get("next_action"), customer.get("next_action_date"),
                customer.get("opportunity_decision"),
            ])

        dark_blue, light_blue, orange = "17365D", "DDEBF7", "F4B183"
        sheet["A1"].font = Font(size=18, bold=True, color="FFFFFF")
        sheet["A1"].fill = PatternFill("solid", fgColor=dark_blue)
        sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=13)
        sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=13)
        for cell in sheet[3]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=dark_blue)
            cell.alignment = Alignment(wrap_text=True)
        for row in sheet.iter_rows(min_row=4, max_row=sheet.max_row, min_col=5, max_col=13):
            for cell in row:
                cell.fill = PatternFill("solid", fgColor=light_blue)
        for row in sheet.iter_rows(min_row=4, max_row=sheet.max_row, min_col=1, max_col=4):
            for cell in row:
                cell.fill = PatternFill("solid", fgColor="F2F2F2")
        sheet.column_dimensions["A"].hidden = True
        widths = [3, 34, 18, 12, 24, 18, 24, 34, 30, 13, 24, 18, 16]
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[chr(64 + index)].width = width
        sheet.freeze_panes = "E4"
        sheet.auto_filter.ref = f"B3:M{sheet.max_row}"

        validations = {
            "E": '"Pendiente,Contacto intentado,Contactado,Aplicación identificada,Sin oportunidad"',
            "J": '"Alto,Medio,Bajo,Ninguno"',
            "K": '"Llamar,Enviar información,Visitar,Levantar datos,Cotizar,Proponer homologación"',
            "M": '"Sí,No,Revisar"',
        }
        for column, formula in validations.items():
            validation = DataValidation(type="list", formula1=formula, allow_blank=True)
            sheet.add_data_validation(validation)
            validation.add(f"{column}4:{column}500")
        for column in ("F", "L"):
            for cell in sheet[column][3:]:
                cell.number_format = "dd/mm/yyyy"

        context = workbook.create_sheet("Contexto")
        context.append(["Cliente", "NIT / ERP", "Asesor", "Última compra", "Ventas otras marcas", "Marcas compradas", "Marcas lineales detectadas"])
        for customer in customers:
            context.append([
                customer["customer_name"], customer["customer_erp_id"], customer["advisor"],
                customer.get("last_purchase"), float(customer.get("other_sales") or 0),
                customer.get("brands") or "", customer.get("competitor_linear_brands") or "Ninguna detectada",
            ])
        for cell in context[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=dark_blue)
        context.freeze_panes = "A2"
        context.auto_filter.ref = context.dimensions
        context.column_dimensions["A"].width = 36
        context.column_dimensions["B"].width = 16
        context.column_dimensions["C"].width = 24
        context.column_dimensions["D"].width = 16
        context.column_dimensions["E"].width = 22
        context.column_dimensions["F"].width = 55
        context.column_dimensions["G"].width = 28
        for cell in context["E"][1:]:
            cell.number_format = '"COP "#,##0'

        guide = workbook.create_sheet("Instrucciones")
        guide.append(["Campaña THK para clientes de plásticos"])
        guide.append(["Objetivo", "Identificar aplicaciones de movimiento lineal y abrir oportunidades de homologación THK."])
        guide.append(["Primer contacto", "30/10/2026"])
        guide.append(["Aplicación identificada", "13/11/2026"])
        guide.append(["Conclusión inicial", "30/11/2026"])
        guide.append(["Qué debe registrar", "Contacto, aplicación o máquina, referencia instalada, interés y próxima acción."])
        guide.append(["Qué ocurre después", "Los clientes marcados como oportunidad pasan al proceso comercial normal del Command Center."])
        guide["A1"].font = Font(size=18, bold=True, color="FFFFFF")
        guide["A1"].fill = PatternFill("solid", fgColor=dark_blue)
        guide.merge_cells("A1:B1")
        for cell in guide["A"][1:]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor=orange)
        guide.column_dimensions["A"].width = 28
        guide.column_dimensions["B"].width = 90
        for row in guide.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

        stream = BytesIO()
        workbook.save(stream)
        stream.seek(0)
        safe_advisor = (advisor or customers[0]["advisor"]).title().replace(" ", "_")
        return stream, f"Campana_THK_Plasticos_{safe_advisor}.xlsx"

    @staticmethod
    @transactional
    def import_workbook(initiative_id: int, file_stream) -> dict[str, int]:
        workbook = load_workbook(file_stream, data_only=False)
        if "Seguimiento" not in workbook.sheetnames:
            raise ValueError("El archivo no contiene la hoja Seguimiento.")
        sheet = workbook["Seguimiento"]
        headers = [cell.value for cell in sheet[3]]
        if headers[: len(TRACKING_HEADERS)] != TRACKING_HEADERS:
            raise ValueError("La estructura del archivo cambió. Descargue una copia nueva.")
        updated = 0
        ignored = 0
        for row in sheet.iter_rows(min_row=4, values_only=True):
            source_key = str(row[0] or "").strip()
            if not source_key:
                continue
            values = {
                "status": row[4], "contact_date": InitiativeCampaignService._date(row[5]),
                "contact_name": row[6], "application": row[7],
                "installed_reference": row[8], "interest": row[9],
                "next_action": row[10], "next_action_date": InitiativeCampaignService._date(row[11]),
                "opportunity_decision": row[12],
            }
            if InitiativeCampaignRepository.update_tracking(initiative_id, source_key, values):
                updated += 1
            else:
                ignored += 1
        InitiativeRepository.create_event(
            initiative_id=initiative_id,
            event_type="campaign_sync",
            title="Seguimiento de campaña sincronizado",
            details=f"{updated} clientes actualizados; {ignored} filas ignoradas.",
            created_by="excel",
        )
        return {"updated": updated, "ignored": ignored}

    @staticmethod
    def _date(value):
        if value is None or value == "":
            return None
        if hasattr(value, "date"):
            return value.date().isoformat()
        return str(value).strip()
