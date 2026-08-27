from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.workspace.connectors.workbook_reader import WorkbookReadError, WorkbookReader


class AgreementWorkbookError(ValueError):
    pass


class AgreementWorkbookParser:
    MAX_ROWS = 5000
    FIELD_ALIASES = {
        "internal_sku": {"sku", "código", "codigo", "material", "item", "numero parte", "número parte", "numero de parte", "part number", "internal sku"},
        "manufacturer_part_number": {"referencia", "referencia skf", "referencia fabricante", "referencia del fabricante", "manufacturer part number", "manufacturer reference", "skf reference"},
        "description": {"descripción", "descripcion", "producto", "product description"},
        "negotiated_price": {"precio especial", "precio acuerdo", "precio convenio", "precio negociado", "fob dd convenio", "special price", "net price", "agreement price", "contract price"},
        "list_price": {"fob dd lista", "precio lista", "list price"},
        "suggested_price": {"precio sugerido", "suggested price"},
        "product_line": {"product line", "linea de producto", "línea de producto", "familia"},
        "spc": {"spc"},
        "unit_of_measure": {"unidad", "unidad de medida", "uom"},
        "notes": {"notas", "observaciones", "notes"},
    }

    @classmethod
    def inspect(cls, path: Path, worksheet: str | None = None) -> dict[str, Any]:
        try:
            workbook = WorkbookReader.read(path, worksheet, cls.MAX_ROWS)
            header_values = workbook["header"]
            if not header_values or not any(cls._text(value) for value in header_values):
                raise AgreementWorkbookError("La hoja seleccionada está vacía.")
            headers = [cls._text(value) or f"Columna {index + 1}" for index, value in enumerate(header_values)]
            rows = [{"source_row_number": number,
                     "values": [cls._value(value) for value in values[:len(headers)]]}
                    for number, values in workbook["rows"]]
            return {"worksheets": workbook["worksheets"],
                    "selected_worksheet": workbook["selected_worksheet"],
                    "headers": headers, "mapping": cls.detect_mapping(headers),
                    "rows": rows,
                    "source_type": workbook.get("source_type", "excel"),
                    "source_table_index": workbook.get("source_table_index"),
                    "detected_metadata": workbook.get("detected_metadata", {}),
                    "worksheet_details": workbook.get("worksheet_details", []),
                    "detected_table_count": workbook.get("detected_table_count", 0)}
        except WorkbookReadError as exc:
            raise AgreementWorkbookError(str(exc)) from exc

    @classmethod
    def detect_mapping(cls, headers: list[str]) -> dict[str, str]:
        candidates: dict[str, list[str]] = {}
        for header in headers:
            normalized = header.strip().lower()
            for field, aliases in cls.FIELD_ALIASES.items():
                if normalized in aliases:
                    candidates.setdefault(field, []).append(header)
        return {field: values[0] for field, values in candidates.items() if len(values) == 1}

    @staticmethod
    def _text(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _value(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
        return value
