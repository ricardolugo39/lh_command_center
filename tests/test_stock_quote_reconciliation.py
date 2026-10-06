import io
import pytest

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


def test_thk_reference_matching_handles_invoice_aliases_and_cut_lengths():
    key = StockQuoteReconciliationService._thk_match_key
    assert key("BTK 1405V-2.6ZZ NUTTHK") == key("BTK1405V-2.6ZZ")
    assert key("C 8THK") == key("CV8")
    assert key("KR 32 PPATHK") == key("CF12-1UU-AB")
    assert key("KR 40 PPATHK") == key("CF18UU-AB")
    assert key("LM 20 UU-OPTHK") == key("LM20NUU-OP")
    assert key("SRS 15 WMUU(GK)THK") == key("SRS15WMUU")
    assert key("SR 15+3000LTHK") == key("SR15-3000LY")
    assert key("TS 2510+3000LTHK") == key("TS2510+2500L")


def test_thk_alignment_aggregates_split_invoice_rows_and_marks_missing_items():
    orders = [
        {"sku": "SHS 35-3000LTHK"},
        {"sku": "LMK 25 LUUTHK"},
    ]
    quoted = (
        {"vendor_sku": "SHS35-3000L", "quantity": 3.0,
         "unit_price": 229.4, "line_total": 688.2, "raw_text": "carton 6"},
        {"vendor_sku": "SHS35-3000L", "quantity": 4.0,
         "unit_price": 229.4, "line_total": 917.6, "raw_text": "carton 8"},
    )
    aligned = StockQuoteReconciliationService._align_lines(orders, quoted)
    assert aligned[0]["quantity"] == 7
    assert aligned[0]["line_total"] == pytest.approx(1605.8)
    assert aligned[1]["quantity"] == 0
    assert "no encontrada" in aligned[1]["raw_text"]
