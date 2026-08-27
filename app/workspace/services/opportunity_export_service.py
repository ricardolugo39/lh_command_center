import io
from copy import copy
from datetime import date
from typing import Any, Mapping

import pandas as pd

from app.workspace.services.opportunity_list_service import OpportunityListService


class OpportunityExportService:
    HEADERS = {
        "id": "ID",
        "origin_reference": "Referencia CRM",
        "name": "Oportunidad",
        "customer_name": "Cliente",
        "sales_rep": "Vendedor",
        "office": "Sede",
        "status_label": "Etapa Command Center",
        "crm_status": "Estado CRM",
        "crm_stage": "Etapa CRM",
        "crm_source_date": "Fecha CRM",
        "crm_close_date": "Cierre previsto CRM",
        "commercial_value": "Valor comercial",
        "value_source": "Fuente del valor",
        "health": "Salud",
        "next_action_date": "Próxima acción",
        "current_blocker": "Bloqueo actual",
        "last_activity_at": "Última actividad",
    }

    @classmethod
    def build(cls, query: Mapping[str, Any]) -> tuple[io.BytesIO, str]:
        page = OpportunityListService.get_page(query)
        rows = [cls._row(item) for item in page["opportunities"]]
        frame = pd.DataFrame(rows, columns=list(cls.HEADERS.values()))
        stream = io.BytesIO()
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            frame.to_excel(writer, index=False, sheet_name="Oportunidades", startrow=3)
            sheet = writer.book["Oportunidades"]
            sheet["A1"] = "Pipeline de oportunidades"
            sheet["A2"] = (
                f"Sede: {page['filters']['office'] or 'Todas'} · "
                f"Exportado: {date.today().isoformat()} · "
                f"Registros: {len(rows)}"
            )
            title_font = copy(sheet["A1"].font)
            title_font.bold = True
            title_font.size = 16
            sheet["A1"].font = title_font
            sheet.freeze_panes = "A5"
            last_column = sheet.cell(row=4, column=len(frame.columns)).column_letter
            sheet.auto_filter.ref = f"A4:{last_column}{4 + len(frame)}"
            for cell in sheet[4]:
                font = copy(cell.font)
                font.bold = True
                font.color = "FFFFFF"
                cell.font = font
                cell.fill = __import__("openpyxl").styles.PatternFill(
                    "solid", fgColor="246DD8"
                )
            date_headers = {"Fecha CRM", "Cierre previsto CRM", "Próxima acción"}
            for column in sheet.columns:
                header = sheet.cell(row=4, column=column[0].column).value
                width = min(
                    42,
                    max(12, max(len(str(cell.value or "")) for cell in column) + 2),
                )
                sheet.column_dimensions[column[0].column_letter].width = width
                if header in date_headers:
                    for cell in column[4:]:
                        cell.number_format = "yyyy-mm-dd"
            value_column = list(cls.HEADERS.values()).index("Valor comercial") + 1
            for cell in sheet.iter_cols(
                min_col=value_column, max_col=value_column, min_row=5
            ):
                for item in cell:
                    item.number_format = '#,##0.00'
        stream.seek(0)
        return stream, f"oportunidades-{page['filters']['office'] or 'todas'}-{date.today().isoformat()}.xlsx"

    @staticmethod
    def _row(item: dict[str, Any]) -> dict[str, Any]:
        value = item.get("commercial_amount")
        source = "Monto aprobado"
        if value in (None, "") and item.get("quote"):
            value = item["quote"].get("normalized_amount")
            source = "Cotización"
        if value in (None, ""):
            value = item.get("crm_potential_value")
            source = "Potencial CRM · por revisar" if value not in (None, "") else "Sin valor"
        return {
            "ID": item.get("id"),
            "Referencia CRM": item.get("origin_reference"),
            "Oportunidad": item.get("name"),
            "Cliente": item.get("customer_name"),
            "Vendedor": item.get("sales_rep"),
            "Sede": item.get("office"),
            "Etapa Command Center": item.get("status_label"),
            "Estado CRM": item.get("crm_status"),
            "Etapa CRM": item.get("crm_stage"),
            "Fecha CRM": OpportunityExportService._date(item.get("crm_source_date")),
            "Cierre previsto CRM": OpportunityExportService._date(item.get("crm_close_date")),
            "Valor comercial": float(value) if value not in (None, "") else None,
            "Fuente del valor": source,
            "Salud": item.get("health", {}).get("label"),
            "Próxima acción": OpportunityExportService._date(item.get("next_action_date")),
            "Bloqueo actual": item.get("current_blocker"),
            "Última actividad": item.get("last_activity_at"),
        }

    @staticmethod
    def _date(value: Any):
        if not value:
            return None
        return pd.to_datetime(value).date()
