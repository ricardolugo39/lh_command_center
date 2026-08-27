from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


class AgreementImportValidator:
    DESTINATIONS = (
        "internal_sku", "manufacturer_part_number", "description",
        "negotiated_price", "list_price", "suggested_price",
        "product_line", "spc", "unit_of_measure", "notes",
    )
    DESTINATION_LABELS = {
        "internal_sku": "SKU interno",
        "manufacturer_part_number": "Referencia del fabricante",
        "description": "Descripción",
        "negotiated_price": "Precio negociado",
        "unit_of_measure": "Unidad de medida",
        "notes": "Notas",
        "list_price": "Precio de lista",
        "suggested_price": "Precio sugerido",
        "product_line": "Línea de producto",
        "spc": "SPC",
    }

    @classmethod
    def validate(cls, metadata: dict[str, Any], parsed: dict[str, Any],
                 mapping: dict[str, str]) -> dict[str, Any]:
        errors = []
        metadata_warnings = []
        for field, label in (("name", "nombre"), ("supplier", "proveedor"),
                             ("currency", "moneda"),
                             ("start_date", "fecha inicial"),
                             ("end_date", "fecha final")):
            if not str(metadata.get(field) or "").strip():
                errors.append(f"El campo {label} es obligatorio.")
        try:
            start = date.fromisoformat(metadata.get("start_date", ""))
            end = date.fromisoformat(metadata.get("end_date", ""))
            if end < start:
                errors.append("La fecha final no puede ser anterior a la fecha inicial.")
        except ValueError:
            if metadata.get("start_date") and metadata.get("end_date"):
                errors.append("Las fechas del acuerdo no son válidas.")
        if not ({"internal_sku", "manufacturer_part_number"} & set(mapping)):
            errors.append("No se encontró una columna que pueda utilizarse como referencia de producto.")
        detected = parsed.get("detected_metadata", {})
        if (
            detected.get("start_date") and detected.get("end_date")
            and (detected["start_date"] != metadata.get("start_date")
                 or detected["end_date"] != metadata.get("end_date"))
        ):
            metadata_warnings.append(
                "El archivo indica una vigencia diferente a la ingresada. Revise las fechas antes de confirmar."
            )
        headers = parsed["headers"]
        invalid_sources = set(mapping.values()) - set(headers)
        if invalid_sources or len(mapping.values()) != len(set(mapping.values())):
            errors.append("El mapeo contiene columnas inválidas o repetidas.")

        indexes = {header: index for index, header in enumerate(headers)}
        rows, seen_exact, seen_references = [], set(), {}
        summary = {"total": len(parsed["rows"]), "valid": 0, "warnings": 0, "errors": 0, "duplicates": 0, "blank": 0}
        for source in parsed["rows"]:
            item = {field: source["values"][indexes[column]] if indexes[column] < len(source["values"]) else None for field, column in mapping.items()}
            item["source_row_number"] = source["source_row_number"]
            if not any(value not in (None, "") for key, value in item.items() if key != "source_row_number"):
                summary["blank"] += 1
                continue
            item_errors, warnings = [], []
            sku = cls._normalize_reference(item.get("internal_sku"))
            manufacturer = cls._normalize_reference(item.get("manufacturer_part_number"))
            item["internal_sku"], item["manufacturer_part_number"] = sku or None, manufacturer or None
            item["normalized_reference"] = sku or manufacturer
            if not item["normalized_reference"]:
                item_errors.append("Falta una referencia de producto.")
            for price_field in ("negotiated_price", "list_price", "suggested_price"):
                price = item.get(price_field)
                if price not in (None, ""):
                    try:
                        price = cls._decimal_price(price)
                        if price < 0: item_errors.append("El precio no puede ser negativo.")
                    except (InvalidOperation, ValueError):
                        item_errors.append("El precio debe ser numérico.")
                        price = None
                else:
                    price = None
                item[price_field] = price
            price = item.get("negotiated_price")
            exact = tuple(item.get(field) for field in cls.DESTINATIONS)
            duplicate = exact in seen_exact
            if duplicate:
                warnings.append("Fila duplicada exacta; no se importará.")
                summary["duplicates"] += 1
            seen_exact.add(exact)
            reference = item.get("normalized_reference")
            if reference and reference in seen_references and not duplicate:
                warnings.append("La referencia se repite con valores comerciales diferentes.")
            if reference: seen_references[reference] = exact
            status = "error" if item_errors else "warning" if warnings else "valid"
            summary["errors" if status == "error" else "warnings" if status == "warning" else "valid"] += 1
            rows.append({**item, "status": status, "errors": item_errors, "warnings": warnings, "duplicate": duplicate})
        return {"blocking_errors": errors, "metadata_warnings": metadata_warnings,
                "rows": rows, "summary": summary,
                "can_confirm": not errors and summary["errors"] == 0
                and any(not row["duplicate"] for row in rows)}

    @staticmethod
    def _normalize_reference(value: Any) -> str:
        return "".join(str(value or "").strip().upper().split())

    @staticmethod
    def _decimal_price(value: Any) -> Decimal:
        text = str(value).replace(" ", "")
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")
        return Decimal(text)
