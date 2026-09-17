from __future__ import annotations

import io
from copy import copy
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app.database.transaction import transaction
from app.workspace.stock_planning.decisions import StockPlanningDecisionService
from app.workspace.stock_planning.forecasting import StockForecastEngine
from app.workspace.stock_planning.repository import StockPlanningRepository
from app.workspace.stock_planning.replenishment import StockReplenishmentService


MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MIMETYPE = "application/pdf"


class StockPlanningExportService:
    @classmethod
    def purchase_order_confirmation_pdf(
        cls, snapshot_id: int,
    ) -> tuple[io.BytesIO, str]:
        page, forecast = cls._data(snapshot_id)
        with transaction(write=False) as connection:
            quotes = [dict(row) for row in connection.execute(
                """SELECT id,branch_code,quote_number,status
                FROM stock_planning_vendor_quotes
                WHERE snapshot_id=? ORDER BY id DESC""",
                (snapshot_id,),
            ).fetchall()]
            vendor_codes = connection.execute(
                """SELECT l.internal_sku,q.branch_code,l.vendor_sku
                FROM stock_planning_vendor_quote_lines l
                JOIN stock_planning_vendor_quotes q ON q.id=l.vendor_quote_id
                JOIN (
                    SELECT branch_code,MAX(id) latest_id
                    FROM stock_planning_vendor_quotes
                    WHERE snapshot_id=? GROUP BY branch_code
                ) latest ON latest.latest_id=q.id""",
                (snapshot_id,),
            ).fetchall()
        latest_quotes = {}
        for quote in quotes:
            latest_quotes.setdefault(str(quote["branch_code"]), quote)
        if not latest_quotes:
            raise ValueError("Primero cargue las cotizaciones del proveedor.")
        if any(row["status"] != "ready" for row in latest_quotes.values()):
            raise ValueError(
                "Resuelva todas las alertas y aclaraciones antes de exportar."
            )

        quoted_codes = {
            (row["internal_sku"], str(row["branch_code"])): row["vendor_sku"]
            for row in vendor_codes if row["vendor_sku"]
        }
        product_codes = {
            item["internal_sku"]: item.get("vendor_sku") or item["internal_sku"]
            for item in page["products"]
        }
        rows_by_branch = {"1": [], "50": []}
        for item in forecast["rows"]:
            branch = str(item["branch"])
            if branch not in rows_by_branch or item["final_quantity"] <= 0:
                continue
            price = item.get("fob_usd")
            rows_by_branch[branch].append({
                "vendor_sku": quoted_codes.get(
                    (item["sku"], branch), product_codes.get(item["sku"], item["sku"])
                ),
                "internal_sku": item["sku"],
                "quantity": int(item["final_quantity"]),
                "unit_price": price,
                "total": float(item["final_quantity"]) * price if price is not None else None,
            })
        if not any(rows_by_branch.values()):
            raise ValueError("No hay líneas confirmadas para exportar.")

        stream = io.BytesIO()
        document = SimpleDocTemplate(
            stream, pagesize=landscape(A4), leftMargin=13 * mm,
            rightMargin=13 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
            title=f"Confirmación de pedido {page['snapshot']['snapshot_key']}",
            author="Lugo Hermanos",
        )
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name="OrderMeta", parent=styles["BodyText"], fontSize=8,
            leading=11, textColor=colors.HexColor("#4B5563"),
        ))
        styles.add(ParagraphStyle(
            name="Amount", parent=styles["BodyText"], alignment=TA_RIGHT,
            fontSize=8,
        ))
        story = [
            Paragraph("LUGO HERMANOS", styles["Title"]),
            Paragraph("CONFIRMACIÓN DE ORDEN DE COMPRA", styles["Heading1"]),
            Paragraph(
                f"Proveedor: {page['snapshot']['vendor_name']}<br/>"
                f"Pedido: {page['snapshot']['snapshot_key']}<br/>"
                f"Fecha de corte: {page['snapshot']['as_of_date']}<br/>"
                "Moneda: USD · Precios unitarios FOB",
                styles["OrderMeta"],
            ),
            Spacer(1, 5 * mm),
        ]
        grand_total = 0.0
        quote_by_branch = {}
        for quote in latest_quotes.values():
            quote_by_branch[str(quote["branch_code"])] = quote["quote_number"]
        for branch, branch_name in (("1", "BOGOTÁ"), ("50", "CALI")):
            branch_rows = sorted(rows_by_branch[branch], key=lambda row: row["internal_sku"])
            if not branch_rows:
                continue
            quote_label = quote_by_branch.get(branch) or "Sin número"
            story.extend([
                Paragraph(
                    f"{branch_name} · Cotización {quote_label}",
                    styles["Heading2"],
                ),
                Spacer(1, 2 * mm),
            ])
            data = [[
                "Ítem", "Referencia Thomson", "Referencia Lugo",
                "Cantidad", "Precio unitario USD", "Total USD",
            ]]
            branch_total = 0.0
            for index, row in enumerate(branch_rows, start=1):
                total = row["total"] or 0
                branch_total += total
                data.append([
                    str(index), row["vendor_sku"], row["internal_sku"],
                    str(row["quantity"]),
                    f"{row['unit_price']:,.2f}" if row["unit_price"] is not None else "Pendiente",
                    f"{row['total']:,.2f}" if row["total"] is not None else "Pendiente",
                ])
            grand_total += branch_total
            data.append(["", "", "", "", "Subtotal", f"{branch_total:,.2f}"])
            table = Table(
                data, repeatRows=1,
                colWidths=[14*mm, 52*mm, 62*mm, 25*mm, 49*mm, 49*mm],
            )
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -2), .35, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F5F7FA")]),
                ("FONTNAME", (4, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (4, -1), (-1, -1), .8, colors.HexColor("#1F4E78")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.extend([table, Spacer(1, 6 * mm)])
        story.extend([
            Paragraph(f"TOTAL CONFIRMADO USD {grand_total:,.2f}", styles["Heading2"]),
            Spacer(1, 4 * mm),
            Paragraph(
                "Este documento confirma únicamente las referencias y cantidades "
                "incluidas. Las líneas excluidas durante la revisión no hacen parte "
                "de esta orden.",
                styles["OrderMeta"],
            ),
        ])

        def footer(canvas, doc):
            canvas.saveState()
            canvas.setFillColor(colors.white)
            canvas.rect(
                0, 0, landscape(A4)[0], landscape(A4)[1],
                stroke=0, fill=1,
            )
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(colors.HexColor("#6B7280"))
            canvas.drawString(13 * mm, 7 * mm, "Generado por LH Command Center")
            canvas.drawRightString(
                landscape(A4)[0] - 13 * mm, 7 * mm, f"Página {doc.page}"
            )
            canvas.restoreState()

        document.build(story, onFirstPage=footer, onLaterPages=footer)
        stream.seek(0)
        return stream, f"confirmacion-pedido-{page['snapshot']['snapshot_key']}.pdf"

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
