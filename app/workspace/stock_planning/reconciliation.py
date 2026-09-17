from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import re
from typing import Any

from pypdf import PdfReader
from werkzeug.utils import secure_filename

from app.database.transaction import transaction
from app.storage import upload_path
from app.workspace.stock_planning.decisions import StockPlanningDecisionService
from app.workspace.stock_planning.forecasting import StockForecastEngine
from app.workspace.stock_planning.repository import StockPlanningRepository


MONEY_PATTERN = re.compile(
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d+)\s+"
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+"
    r"(?:\d+\s+y\s+\d+\s+d[ií]as)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedQuote:
    quote_number: str | None
    quote_date: str | None
    expires_at: str | None
    total: float | None
    lines: tuple[dict[str, Any], ...]


class StockQuoteReconciliationService:
    """Import vendor PDFs and compare them with a frozen purchase snapshot."""

    @classmethod
    def upload(
        cls, snapshot_id: int, branch_code: str, filename: str,
        content: bytes, uploaded_by: str,
    ) -> int:
        branch_code = str(branch_code).strip()
        if branch_code not in {"1", "50"}:
            raise ValueError("Seleccione Bogotá o Cali.")
        if not filename.lower().endswith(".pdf") or not content.startswith(b"%PDF"):
            raise ValueError("La respuesta del proveedor debe ser un PDF válido.")
        if len(content) > 15 * 1024 * 1024:
            raise ValueError("El PDF supera el límite de 15 MB.")

        page = StockPlanningRepository.snapshot_detail(snapshot_id)
        if not page:
            raise ValueError("El análisis de inventario no existe.")
        parsed = cls.parse(content)
        order_rows = cls._order_rows(snapshot_id, branch_code)
        if len(parsed.lines) != len(order_rows):
            raise ValueError(
                "La cotización contiene "
                f"{len(parsed.lines)} línea(s), pero el pedido de la sede tiene "
                f"{len(order_rows)}. Revise que corresponda a este pedido."
            )

        digest = hashlib.sha256(content).hexdigest()
        directory = upload_path("stock-planning", "vendor-quotes", str(snapshot_id))
        directory.mkdir(parents=True, exist_ok=True)
        safe_name = secure_filename(filename) or f"quote-{digest[:12]}.pdf"
        stored = directory / f"{digest[:12]}-{safe_name}"
        if not stored.exists():
            stored.write_bytes(content)

        with transaction(write=True) as connection:
            existing = connection.execute(
                """SELECT id FROM stock_planning_vendor_quotes
                WHERE snapshot_id=? AND branch_code=? AND file_hash=?""",
                (snapshot_id, branch_code, digest),
            ).fetchone()
            if existing:
                return int(existing["id"])
            cursor = connection.execute(
                """INSERT INTO stock_planning_vendor_quotes (
                    snapshot_id,branch_code,quote_number,quote_date,expires_at,
                    quoted_total,original_filename,stored_file_path,file_hash,
                    uploaded_by
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id, branch_code, parsed.quote_number,
                    parsed.quote_date, parsed.expires_at, parsed.total,
                    filename, str(stored), digest, uploaded_by,
                ),
            )
            quote_id = int(cursor.lastrowid)
            for index, (ordered, quoted) in enumerate(
                zip(order_rows, parsed.lines), start=1
            ):
                quoted["vendor_sku"] = cls._vendor_sku(
                    ordered["sku"], quoted.get("raw_text", "")
                )
                comparison = cls._compare(ordered, quoted)
                connection.execute(
                    """INSERT INTO stock_planning_vendor_quote_lines (
                        vendor_quote_id,line_number,internal_sku,vendor_sku,
                        ordered_quantity,quoted_quantity,platform_unit_price,
                        quoted_unit_price,quoted_line_total,calculated_line_total,
                        variance_amount,variance_percent,comparison_status,
                        resolution,resolved_by,resolved_at,raw_text
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                        CASE WHEN ? IS NULL THEN NULL ELSE CURRENT_TIMESTAMP END,?)""",
                    (
                        quote_id, index, ordered["sku"], quoted.get("vendor_sku"),
                        ordered["quantity"], quoted["quantity"],
                        ordered["unit_price"], quoted["unit_price"],
                        quoted["line_total"], comparison["calculated_total"],
                        comparison["variance_amount"],
                        comparison["variance_percent"], comparison["status"],
                        "accept_quote" if comparison["status"] == "matched" else None,
                        uploaded_by if comparison["status"] == "matched" else None,
                        "matched" if comparison["status"] == "matched" else None,
                        quoted.get("raw_text"),
                    ),
                )
            cls._refresh_status(connection, quote_id)
        return quote_id

    @staticmethod
    def parse(content: bytes) -> ParsedQuote:
        from io import BytesIO

        try:
            reader = PdfReader(BytesIO(content))
            text = "\n".join(
                page.extract_text(extraction_mode="layout") or ""
                for page in reader.pages
            )
        except Exception as exception:
            raise ValueError("No fue posible leer el PDF.") from exception
        if not text.strip():
            raise ValueError("El PDF no contiene texto legible.")

        lines = []
        for match in MONEY_PATTERN.finditer(text):
            start = text.rfind("\n", 0, match.start()) + 1
            end = text.find("\n", match.end())
            raw = text[start:(len(text) if end < 0 else end)].strip()
            lines.append({
                "unit_price": cls_number(match.group(1)),
                "quantity": float(match.group(2)),
                "line_total": cls_number(match.group(3)),
                "raw_text": raw,
            })
        quote = re.search(r"Presupuesto\s+N[°º]:\s*([A-Z0-9-]+)", text, re.I)
        quote_date = re.search(r"Fecha:\s*(\d{2}/\d{2}/\d{4})", text, re.I)
        expiry = re.search(r"Expira\s+en:\s*(\d{2}/\d{2}/\d{4})", text, re.I)
        total_matches = re.findall(
            r"TOTAL\s*\(USD\):\s*(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.I
        )
        return ParsedQuote(
            quote.group(1) if quote else None,
            iso_date(quote_date.group(1)) if quote_date else None,
            iso_date(expiry.group(1)) if expiry else None,
            cls_number(total_matches[-1]) if total_matches else None,
            tuple(lines),
        )

    @staticmethod
    def _order_rows(snapshot_id: int, branch_code: str) -> list[dict[str, Any]]:
        forecast = StockPlanningDecisionService.present(
            snapshot_id, StockForecastEngine.analyze(snapshot_id)
        )
        return sorted(({
            "sku": row["sku"],
            "quantity": float(row["final_quantity"]),
            "unit_price": (
                float(row["fob_usd"]) if row.get("fob_usd") is not None else None
            ),
        } for row in forecast["rows"]
            if str(row["branch"]) == branch_code
            and float(row["final_quantity"]) > 0), key=lambda row: row["sku"])

    @staticmethod
    def _compare(ordered: dict[str, Any], quoted: dict[str, Any]) -> dict[str, Any]:
        quantity = float(quoted["quantity"])
        price = float(quoted["unit_price"])
        calculated = quantity * price
        platform = ordered["unit_price"]
        variance = price - platform if platform is not None else None
        percent = (
            variance / platform * 100 if platform not in (None, 0) else None
        )
        total_error = abs(float(quoted["line_total"]) - calculated)
        tolerance = max(.25, quantity * .02)
        expected_vendor_sku = re.sub(
            r"\s+", "", ordered["sku"].upper()
        ).removesuffix("THO")
        quoted_vendor_sku = str(quoted.get("vendor_sku") or "").upper()
        if quantity != float(ordered["quantity"]):
            status = "quantity_mismatch"
        elif (
            ordered["sku"].upper().startswith("411 ")
            and quoted_vendor_sku
            and quoted_vendor_sku != expected_vendor_sku
        ):
            status = "possible_substitution"
        elif total_error > tolerance:
            status = "line_total_error"
        elif variance is None or abs(variance) > .005:
            status = "price_change"
        else:
            status = "matched"
        return {
            "calculated_total": calculated, "variance_amount": variance,
            "variance_percent": percent, "status": status,
        }

    @staticmethod
    def _vendor_sku(internal_sku: str, raw_text: str) -> str | None:
        tokens = [re.escape(token) for token in internal_sku.split()]
        pattern = r"\s+".join(tokens)
        match = re.search(pattern + r"\s+([A-Z0-9.+/_=-]+)", raw_text, re.I)
        return match.group(1).upper() if match else None

    @classmethod
    def detail(cls, snapshot_id: int, quote_id: int | None = None) -> dict[str, Any]:
        with transaction(write=False) as connection:
            quotes = [dict(row) for row in connection.execute(
                """SELECT * FROM stock_planning_vendor_quotes
                WHERE snapshot_id=? ORDER BY uploaded_at DESC,id DESC""",
                (snapshot_id,),
            ).fetchall()]
            selected = next((row for row in quotes if row["id"] == quote_id), None)
            if selected is None and quotes:
                selected = quotes[0]
            lines = [] if not selected else [dict(row) for row in connection.execute(
                """SELECT * FROM stock_planning_vendor_quote_lines
                WHERE vendor_quote_id=? ORDER BY line_number""",
                (selected["id"],),
            ).fetchall()]
        unresolved = sum(row["resolution"] is None for row in lines)
        return {
            "quotes": quotes, "quote": selected, "lines": lines,
            "unresolved": unresolved,
            "platform_total": sum(
                (row["platform_unit_price"] or 0) * row["ordered_quantity"]
                for row in lines
            ),
            "calculated_quote_total": sum(
                row["quoted_unit_price"] * row["quoted_quantity"] for row in lines
            ),
        }

    @classmethod
    def resolve(
        cls, snapshot_id: int, quote_line_id: int, resolution: str,
        resolved_by: str, note: str = "",
    ) -> int:
        allowed = {"accept_quote", "keep_platform", "request_clarification"}
        if resolution not in allowed:
            raise ValueError("Seleccione una resolución válida.")
        with transaction(write=True) as connection:
            line = connection.execute(
                """SELECT l.*,q.snapshot_id,q.branch_code,q.id quote_id
                FROM stock_planning_vendor_quote_lines l
                JOIN stock_planning_vendor_quotes q ON q.id=l.vendor_quote_id
                WHERE l.id=? AND q.snapshot_id=?""",
                (quote_line_id, snapshot_id),
            ).fetchone()
            if not line:
                raise ValueError("La línea de conciliación no existe.")
            connection.execute(
                """UPDATE stock_planning_vendor_quote_lines
                SET resolution=?,resolution_note=?,resolved_by=?,
                    resolved_at=CURRENT_TIMESTAMP WHERE id=?""",
                (resolution, note or None, resolved_by, quote_line_id),
            )
            if resolution == "accept_quote":
                connection.execute(
                    """INSERT INTO stock_planning_quote_price_history (
                        snapshot_id,vendor_quote_id,quote_line_id,branch_code,
                        internal_sku,previous_fob_usd,accepted_fob_usd,accepted_by
                    ) VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(quote_line_id) DO UPDATE SET
                        accepted_fob_usd=excluded.accepted_fob_usd,
                        accepted_by=excluded.accepted_by,
                        accepted_at=CURRENT_TIMESTAMP""",
                    (
                        snapshot_id, line["quote_id"], quote_line_id,
                        line["branch_code"], line["internal_sku"],
                        line["platform_unit_price"], line["quoted_unit_price"],
                        resolved_by,
                    ),
                )
            else:
                connection.execute(
                    "DELETE FROM stock_planning_quote_price_history WHERE quote_line_id=?",
                    (quote_line_id,),
                )
            cls._refresh_status(connection, int(line["quote_id"]))
            return int(line["quote_id"])

    @classmethod
    def resolve_many(
        cls, snapshot_id: int, quote_line_ids: list[int], resolution: str,
        resolved_by: str,
    ) -> tuple[int, int]:
        unique_ids = list(dict.fromkeys(quote_line_ids))
        if not unique_ids:
            raise ValueError("Seleccione al menos una línea pendiente.")

        placeholders = ",".join("?" for _ in unique_ids)
        with transaction() as connection:
            rows = connection.execute(
                f"""SELECT l.id,q.id quote_id
                FROM stock_planning_vendor_quote_lines l
                JOIN stock_planning_vendor_quotes q ON q.id=l.vendor_quote_id
                WHERE q.snapshot_id=? AND l.id IN ({placeholders})""",
                (snapshot_id, *unique_ids),
            ).fetchall()
        if len(rows) != len(unique_ids):
            raise ValueError("Una de las líneas seleccionadas ya no está disponible.")
        quote_ids = {int(row["quote_id"]) for row in rows}
        if len(quote_ids) != 1:
            raise ValueError("Seleccione líneas de una sola cotización.")

        for line_id in unique_ids:
            cls.resolve(snapshot_id, line_id, resolution, resolved_by)
        return quote_ids.pop(), len(unique_ids)

    @staticmethod
    def _refresh_status(connection, quote_id: int) -> None:
        unresolved = connection.execute(
            """SELECT COUNT(*) FROM stock_planning_vendor_quote_lines
            WHERE vendor_quote_id=? AND resolution IS NULL""", (quote_id,),
        ).fetchone()[0]
        clarification = connection.execute(
            """SELECT COUNT(*) FROM stock_planning_vendor_quote_lines
            WHERE vendor_quote_id=? AND resolution='request_clarification'""",
            (quote_id,),
        ).fetchone()[0]
        status = "ready" if unresolved == 0 and clarification == 0 else "review"
        connection.execute(
            "UPDATE stock_planning_vendor_quotes SET status=? WHERE id=?",
            (status, quote_id),
        )


def cls_number(value: str) -> float:
    return float(value.replace(".", "").replace(",", "."))


def iso_date(value: str) -> str:
    return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
