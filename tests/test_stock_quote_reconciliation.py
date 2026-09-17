import io

from reportlab.pdfgen import canvas

from app.workspace.stock_planning.reconciliation import (
    StockQuoteReconciliationService,
)


def _quote_pdf():
    stream = io.BytesIO()
    document = canvas.Canvas(stream)
    document.drawString(40, 800, "Presupuesto N°: LA260901-LS01")
    document.drawString(40, 780, "Fecha: 15/09/2026")
    document.drawString(40, 760, "Expira en: 15/10/2026")
    document.drawString(
        40, 720,
        "1 411 N45 A0THO 411N45B0 Producto 94,45 2 188,90 35 y 45 días",
    )
    document.drawString(40, 680, "TOTAL (USD): 188,90")
    document.save()
    return stream.getvalue()


def test_parser_extracts_quote_metadata_and_lines():
    parsed = StockQuoteReconciliationService.parse(_quote_pdf())

    assert parsed.quote_number == "LA260901-LS01"
    assert parsed.quote_date == "2026-09-15"
    assert parsed.expires_at == "2026-10-15"
    assert parsed.total == 188.90
    assert len(parsed.lines) == 1
    assert parsed.lines[0]["quantity"] == 2
    assert parsed.lines[0]["unit_price"] == 94.45


def test_comparison_detects_price_quantity_total_and_substitution():
    ordered = {"sku": "411 N45 A0THO", "quantity": 2, "unit_price": 90}
    base = {
        "quantity": 2, "unit_price": 94.45, "line_total": 188.90,
        "vendor_sku": "411N45A0",
    }
    assert StockQuoteReconciliationService._compare(
        ordered, dict(base)
    )["status"] == "price_change"

    quantity = dict(base, quantity=3)
    assert StockQuoteReconciliationService._compare(
        ordered, quantity
    )["status"] == "quantity_mismatch"

    total = dict(base, line_total=250)
    assert StockQuoteReconciliationService._compare(
        ordered, total
    )["status"] == "line_total_error"

    substitution = dict(base, vendor_sku="411N45B0")
    assert StockQuoteReconciliationService._compare(
        ordered, substitution
    )["status"] == "possible_substitution"


def test_vendor_sku_is_read_after_customer_reference():
    raw = "1 411 N45 A0THO 411N45B0 Producto 94,45 2 188,90"
    assert StockQuoteReconciliationService._vendor_sku(
        "411 N45 A0THO", raw
    ) == "411N45B0"
