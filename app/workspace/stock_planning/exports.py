from __future__ import annotations

import io
from copy import copy
from typing import Any

import pandas as pd

from app.workspace.stock_planning.decisions import StockPlanningDecisionService
from app.workspace.stock_planning.forecasting import StockForecastEngine
from app.workspace.stock_planning.repository import StockPlanningRepository
from app.workspace.stock_planning.replenishment import StockReplenishmentService


MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class StockPlanningExportService:
    @classmethod
    def replenishment_uncovered(cls, snapshot_id: int) -> tuple[io.BytesIO, str]:
        page = StockPlanningRepository.snapshot_detail(snapshot_id)
        if not page or page["snapshot"].get("planning_purpose") != "replenishment":
            raise ValueError("El reporte de reabastecimiento no existe.")
        report = StockReplenishmentService.report(snapshot_id)
        rows = [{
            "Referencia": item["internal_sku"],
            "Frecuencia Cali (meses con venta / 24)": item["active_months_24"],
            "Ventas Cali últimos 12 meses": item["sales_12"],
            "Inventario utilizable Cali": item["cali_inventory"],
            "Tránsito Cali": item["cali_transit"],
            "Inventario utilizable Bogotá": item["bogota_inventory"],
            "Faltante no cubierto": int(item["suggested_quantity"]),
            "Responsable": item.get("assigned_to") or "Sin asignar",
            "Explicación": item["reason"],
        } for item in report["uncovered"]]
        return cls._workbook(
            rows, "Faltantes no cubiertos", page,
            "faltantes-cali-para-compras",
        )

    @classmethod
    def purchase_order(cls, snapshot_id: int) -> tuple[io.BytesIO, str]:
        page, forecast = cls._data(snapshot_id)
        if not forecast["purchase_export_ready"]:
            raise ValueError("Todavía hay compras pendientes de aprobación.")
        vendor_skus = {
            item["internal_sku"]: item.get("vendor_sku") or item["internal_sku"]
            for item in page["products"]
        }
        rows = []
        for item in forecast["rows"]:
            if item["recommended_order"] <= 0 or item["final_quantity"] <= 0:
                continue
            rows.append({
                "Bodega": cls._branch(item["branch"]),
                "Código bodega": item["branch"],
                "Referencia proveedor": vendor_skus.get(item["sku"], item["sku"]),
                "Referencia interna": item["sku"],
                "Cantidad aprobada": int(item["final_quantity"]),
                "Unidad": (
                    f"Barra {item['purchase_length_mm'] / 1000:g} m"
                    if item.get("purchase_length_mm") else "Unidad"
                ),
                "Inventario utilizable": item["usable"],
                "En tránsito": item["transit"],
                "Cantidad sugerida": item["recommended_order"],
                "FOB unitario USD": item.get("fob_usd"),
                "Total FOB USD": item.get("total_fob_usd"),
                "Observación FOB": (
                    "" if item.get("fob_usd") is not None else "Sin precio FOB"
                ),
                "Estado decisión": cls._status(item),
            })
        return cls._workbook(
            rows, "Pedido proveedor", page, "pedido-proveedor"
        )

    @classmethod
    def transfers(cls, snapshot_id: int) -> tuple[io.BytesIO, str]:
        page, forecast = cls._data(snapshot_id)
        replenishment = (
            page["snapshot"].get("planning_purpose") == "replenishment"
        )
        if not replenishment and not forecast["transfer_export_ready"]:
            raise ValueError("Todavía hay traslados pendientes de aprobación.")
        rows = [{
            "Referencia": item["sku"],
            "Desde": cls._branch(item["from_branch"]),
            "Código origen": item["from_branch"],
            "Hacia": cls._branch(item["to_branch"]),
            "Código destino": item["to_branch"],
            "Cantidad aprobada": int(item["final_quantity"]),
            "Movimiento previo": cls._internal_move_note(item),
            "Tipo de aprobación": cls._transfer_approval_type(item),
        } for item in forecast.get("transfers", [])
            if item["final_quantity"] > 0
            and (not replenishment or (
                item.get("decision")
                and item.get("from_branch") == "1"
                and item.get("to_branch") == "50"
            ))]
        if not rows:
            raise ValueError("No hay traslados aprobados para exportar.")
        columns = [
            "Referencia", "Desde", "Código origen", "Hacia",
            "Código destino", "Cantidad aprobada",
            "Movimiento previo",
        ]
        if replenishment:
            columns.append("Tipo de aprobación")
            return cls._multi_sheet_workbook(
                [("Bogotá a Cali", "Traslados aprobados Bogotá → Cali", rows)],
                columns, page, "traslados-bogota-cali",
            )
        sheets = [
            (
                "Despachos desde Cali", "Traslados que despacha Cali",
                [row for row in rows if row["Código origen"] == "50"],
            ),
            (
                "Despachos desde Bogotá", "Traslados que despacha Bogotá",
                [row for row in rows if row["Código origen"] == "1"],
            ),
        ]
        return cls._multi_sheet_workbook(
            sheets, columns, page, "traslados-internos"
        )

    @staticmethod
    def _transfer_approval_type(item: dict[str, Any]) -> str:
        decision = item.get("decision") or {}
        if decision.get("decided_by") == "sistema-quincenal":
            return "Automática"
        if decision.get("decision_status") == "changed":
            return "Modificada manualmente"
        if decision:
            return "Aprobada manualmente"
        return "Pendiente"

    @staticmethod
    def _status(item: dict[str, Any]) -> str:
        decision = item.get("decision")
        if not decision:
            return "Aprobado automáticamente"
        return {
            "approved": "Aprobado", "changed": "Modificado",
            "rejected": "No realizar",
        }[decision["decision_status"]]

    @classmethod
    def _data(cls, snapshot_id):
        page = StockPlanningRepository.snapshot_detail(snapshot_id)
        if not page:
            raise ValueError("El análisis no existe.")
        forecast = StockPlanningDecisionService.present(
            snapshot_id, StockForecastEngine.analyze(snapshot_id)
        )
        return page, forecast

    @staticmethod
    def _branch(code: str) -> str:
        return "Bogotá" if str(code) == "1" else "Cali" if str(code) == "50" else str(code)

    @staticmethod
    def _internal_move_note(item: dict[str, Any]) -> str:
        if item.get("from_branch") != "1" or item.get("to_branch") != "50":
            return ""
        approved = int(item.get("final_quantity") or 0)
        internal = min(approved, int(item.get("internal_move_16_to_1") or 0))
        if internal <= 0:
            return "Mercancía disponible en bodega 1"
        return f"Mover primero {internal} unidad(es) de bodega 16 (KR 68) a bodega 1"

    @staticmethod
    def _workbook(rows, sheet_name, page, prefix):
        if not rows:
            raise ValueError("No hay cantidades aprobadas para exportar.")
        stream = io.BytesIO()
        frame = pd.DataFrame(rows)
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            frame.to_excel(writer, index=False, sheet_name=sheet_name, startrow=4)
            sheet = writer.book[sheet_name]
            sheet["A1"] = f"{sheet_name} · {page['snapshot']['vendor_name']}"
            sheet["A2"] = f"Análisis: {page['snapshot']['snapshot_key']}"
            sheet["A3"] = f"Fecha de corte: {page['snapshot']['as_of_date']}"
            title_font = copy(sheet["A1"].font)
            title_font.bold = True
            title_font.size = 16
            sheet["A1"].font = title_font
            sheet.freeze_panes = "A6"
            last_column = sheet.cell(row=5, column=len(frame.columns)).column_letter
            sheet.auto_filter.ref = f"A5:{last_column}{5 + len(frame)}"
            for cell in sheet[5]:
                font = copy(cell.font)
                font.bold = True
                font.color = "FFFFFF"
                cell.font = font
                cell.fill = __import__("openpyxl").styles.PatternFill("solid", fgColor="206BC4")
            for column in sheet.columns:
                width = min(42, max(12, max(len(str(cell.value or "")) for cell in column) + 2))
                sheet.column_dimensions[column[0].column_letter].width = width
        stream.seek(0)
        return stream, f"{prefix}-{page['snapshot']['snapshot_key']}.xlsx"

    @staticmethod
    def _multi_sheet_workbook(sheets, columns, page, prefix):
        stream = io.BytesIO()
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            for sheet_name, title, rows in sheets:
                frame = pd.DataFrame(rows, columns=columns)
                frame.to_excel(
                    writer, index=False, sheet_name=sheet_name, startrow=4
                )
                sheet = writer.book[sheet_name]
                sheet["A1"] = f"{title} · {page['snapshot']['vendor_name']}"
                sheet["A2"] = (
                    f"Análisis: {page['snapshot']['snapshot_key']}"
                )
                sheet["A3"] = (
                    f"Fecha de corte: {page['snapshot']['as_of_date']}"
                )
                title_font = copy(sheet["A1"].font)
                title_font.bold = True
                title_font.size = 16
                sheet["A1"].font = title_font
                sheet.freeze_panes = "A6"
                last_column = sheet.cell(
                    row=5, column=len(columns)
                ).column_letter
                last_row = max(5, 5 + len(frame))
                sheet.auto_filter.ref = f"A5:{last_column}{last_row}"
                for cell in sheet[5]:
                    font = copy(cell.font)
                    font.bold = True
                    font.color = "FFFFFF"
                    cell.font = font
                    cell.fill = __import__("openpyxl").styles.PatternFill(
                        "solid", fgColor="206BC4"
                    )
                for column in sheet.columns:
                    width = min(
                        42,
                        max(
                            12,
                            max(len(str(cell.value or "")) for cell in column)
                            + 2,
                        ),
                    )
                    sheet.column_dimensions[
                        column[0].column_letter
                    ].width = width
        stream.seek(0)
        return stream, f"{prefix}-{page['snapshot']['snapshot_key']}.xlsx"
