from __future__ import annotations

import io
from copy import copy
from typing import Any

import pandas as pd

from app.workspace.stock_planning.decisions import StockPlanningDecisionService
from app.workspace.stock_planning.forecasting import StockForecastEngine
from app.workspace.stock_planning.repository import StockPlanningRepository


MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class StockPlanningExportService:
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
                "Unidad": "Barra 3 m" if item.get("length_transformation") else "Unidad",
                "Inventario utilizable": item["usable"],
                "En tránsito": item["transit"],
                "Cantidad sugerida": item["recommended_order"],
                "Estado decisión": cls._status(item),
            })
        return cls._workbook(
            rows, "Pedido proveedor", page, "pedido-proveedor"
        )

    @classmethod
    def transfers(cls, snapshot_id: int) -> tuple[io.BytesIO, str]:
        page, forecast = cls._data(snapshot_id)
        if not forecast["transfer_export_ready"]:
            raise ValueError("Todavía hay traslados pendientes de aprobación.")
        rows = [{
            "Referencia": item["sku"],
            "Desde": cls._branch(item["from_branch"]),
            "Código origen": item["from_branch"],
            "Hacia": cls._branch(item["to_branch"]),
            "Código destino": item["to_branch"],
            "Cantidad aprobada": int(item["final_quantity"]),
            "Cantidad sugerida": item["quantity"],
            "Compra evitada": min(item["avoided_purchase"], item["final_quantity"]),
            "Estado decisión": cls._status(item),
        } for item in forecast.get("transfers", []) if item["final_quantity"] > 0]
        return cls._workbook(rows, "Traslados", page, "traslados-internos")

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
