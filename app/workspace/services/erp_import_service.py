from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.database.transaction import transaction
from app.storage import upload_path
from app.loaders.raw_sales_loader import normalize_raw_sales, read_file
from app.loaders.inventory_snapshot_loader import (
    InventoryIssue,
    normalize_inventory,
    read_inventory_file,
)
from app.pipelines.customer_dimension_pipeline import CustomerDimensionPipeline
from app.workspace.repositories.erp_import_repository import ERPImportRepository
from app.workspace.customer_identity import (
    customer_site_key, normalize_nit, normalize_site_text,
)


class ERPImportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ImportPreview:
    execution_id: int
    import_type: str
    original_filename: str
    rows_read: int
    columns: tuple[str, ...]
    sample_rows: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    file_hash: str
    header_mapping: tuple[tuple[str, str], ...]
    sync_metrics: dict[str, Any]
    validation_issues: tuple[dict[str, Any], ...]
    can_confirm: bool
    snapshot_date: str | None


class ERPImportService:
    SCHEMA_VERSION = "erp-v1"
    ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
    SALES_REQUIRED = {
        "nit", "razonsocial", "prefijo", "numero", "fecha", "idproducto",
        "nombreproducto", "cantidad", "idfam1", "idfam2", "valorbruto", "costo",
    }
    CUSTOMER_REQUIRED = {
        "nit", "razonsocial", "ciudad", "direccion1", "vendedor", "cliente_credito",
        "cupocreditocc", "plazopagocc", "idciiu",
    }
    FOB_PRICE_REQUIRED = {
        "idproducto", "prefijo", "sufijo", "idfam2", "fob", "lista1", "nit",
    }
    STORAGE_ROOT = upload_path("erp-imports")

    @classmethod
    def prepare(
        cls, *, import_type: str, upload: FileStorage, executed_by: str,
        snapshot_date: str | None = None,
    ) -> ImportPreview:
        cls._validate_type(import_type)
        normalized_snapshot_date = cls._snapshot_date(
            import_type, snapshot_date
        )
        if not upload or not upload.filename:
            raise ERPImportValidationError("Seleccione un archivo para importar.")
        extension = Path(upload.filename).suffix.lower()
        if extension not in cls.ALLOWED_EXTENSIONS:
            raise ERPImportValidationError(
                "Formato no soportado. Use archivos .xlsx, .xls o .csv."
            )

        original = secure_filename(upload.filename)
        cls.STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        staged = cls.STORAGE_ROOT / f"pending-{original}"
        upload.save(staged)
        file_hash = cls._hash(staged)
        stored = cls.STORAGE_ROOT / f"{file_hash}{extension}"
        if stored.exists():
            staged.unlink()
        else:
            staged.replace(stored)

        try:
            dataframe = cls._read(import_type, stored)
            normalized, warnings, header_mapping, issues = cls._validate_with_issues(
                import_type, dataframe, normalized_snapshot_date
            )
        except Exception as error:
            with transaction():
                ERPImportRepository.create_execution({
                    "import_type": import_type,
                    "original_filename": upload.filename,
                    "stored_file_path": str(stored),
                    "file_hash": file_hash,
                    "schema_version": cls.SCHEMA_VERSION,
                    "status": "failed",
                    "rows_read": 0,
                    "errors": [str(error)],
                    "executed_by": executed_by or "system",
                    "snapshot_date": normalized_snapshot_date,
                    "log": {"phase": "validation", "error": str(error)},
                })
            raise

        with transaction():
            if import_type == "customers":
                sync_metrics = cls._customer_sync_plan(normalized)["metrics"]
            elif import_type == "inventory":
                sync_metrics = cls._inventory_plan(normalized)
                if sync_metrics["existing_keys"]:
                    warnings.append(
                        f"{sync_metrics['existing_keys']} combinaciones "
                        "bodega + producto ya existen para este snapshot. "
                        "La confirmación permitirá sobrescribirlas."
                    )
                if sync_metrics["new_warehouses"]:
                    warnings.append(
                        "Bodegas no vistas anteriormente: "
                        + ", ".join(sync_metrics["new_warehouse_codes"])
                    )
            elif import_type == "fob_prices":
                sync_metrics = cls._fob_price_plan(normalized)
            else:
                sync_metrics = {}
            execution_id = ERPImportRepository.create_execution({
                "import_type": import_type,
                "original_filename": upload.filename,
                "stored_file_path": str(stored),
                "file_hash": file_hash,
                "schema_version": cls.SCHEMA_VERSION,
                "status": "previewed",
                "rows_read": len(normalized),
                "warnings": warnings,
                "executed_by": executed_by or "system",
                "snapshot_date": normalized_snapshot_date,
                "log": {
                    "phase": "preview",
                    "columns": list(normalized.columns),
                    "header_mapping": header_mapping,
                    "metrics": sync_metrics,
                },
                **sync_metrics,
            })
            ERPImportRepository.create_issues(execution_id, issues)
        return cls._preview(execution_id, import_type, upload.filename,
                            file_hash, normalized, warnings, header_mapping,
                            sync_metrics, issues, normalized_snapshot_date)

    @classmethod
    def confirm(
        cls, execution_id: int, *, overwrite_existing: bool = False
    ) -> dict[str, Any]:
        execution = ERPImportRepository.get_execution(execution_id)
        if not execution:
            raise ERPImportValidationError("La importación no existe.")
        if execution["status"] != "previewed":
            raise ERPImportValidationError(
                "Esta importación ya fue procesada o no puede confirmarse."
            )
        import_type = execution["import_type"]
        path = Path(execution["stored_file_path"])
        dataframe = cls._read(import_type, path)
        normalized, warnings, _header_mapping, issues = cls._validate_with_issues(
            import_type, dataframe, execution.get("snapshot_date")
        )
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            raise ERPImportValidationError(
                "La importación contiene errores de validación y no puede confirmarse."
            )
        if import_type == "inventory":
            plan = cls._inventory_plan(normalized)
            if plan["existing_keys"] and not overwrite_existing:
                raise ERPImportValidationError(
                    f"{plan['existing_keys']} filas ya existen para la fecha "
                    "del snapshot. Confirme explícitamente la sobrescritura."
                )

        try:
            with transaction():
                ERPImportRepository.update_execution(
                    execution_id, {"status": "processing"}
                )
                if import_type == "sales":
                    metrics = cls._import_sales(normalized)
                elif import_type == "inventory":
                    metrics = cls._import_inventory(
                        normalized, execution["original_filename"]
                    )
                elif import_type == "fob_prices":
                    metrics = cls._import_fob_prices(execution_id, normalized)
                else:
                    metrics = cls._import_customers(normalized)
                ERPImportRepository.update_execution(execution_id, {
                    "status": "completed",
                    "rows_read": len(normalized),
                    **metrics,
                    "warnings": warnings,
                    "completed_at": ERPImportRepository.completed_at(),
                    "log": {
                        "phase": "completed", "metrics": metrics,
                        "header_mapping": _header_mapping,
                    },
                })
        except Exception as error:
            with transaction():
                ERPImportRepository.update_execution(execution_id, {
                    "status": "failed",
                    "errors": [str(error)],
                    "completed_at": ERPImportRepository.completed_at(),
                    "log": {"phase": "failed", "error": str(error)},
                })
            raise

        # The dimension is a rebuildable read model. Refresh only after the
        # authoritative customer UPSERT has committed successfully.
        if import_type == "customers":
            CustomerDimensionPipeline().run()
        return ERPImportRepository.get_execution(execution_id) or {}

    @staticmethod
    def history() -> list[dict[str, Any]]:
        return ERPImportRepository.list_executions()

    @staticmethod
    def detail(execution_id: int) -> dict[str, Any] | None:
        value = ERPImportRepository.get_execution(execution_id)
        if not value:
            return None
        for source, target in (
            ("warnings_json", "warnings"),
            ("errors_json", "errors"),
            ("execution_log_json", "log"),
        ):
            try:
                default = "{}" if source == "execution_log_json" else "[]"
                value[target] = json.loads(value.get(source) or default)
            except json.JSONDecodeError:
                value[target] = [] if source != "execution_log_json" else {}
        value["issues"] = ERPImportRepository.list_issues(execution_id)
        return value

    @classmethod
    def _import_sales(cls, dataframe: pd.DataFrame) -> dict[str, int]:
        records = cls._records(dataframe)
        unique: dict[str, dict[str, Any]] = {}
        for row in records:
            unique.setdefault(row["sales_line_key"], row)
        duplicate_in_file = len(records) - len(unique)
        existing = ERPImportRepository.existing_sales_keys(unique)
        pending = [row for key, row in unique.items() if key not in existing]
        inserted = ERPImportRepository.insert_sales(pending)
        duplicates = duplicate_in_file + len(existing)
        return {
            "rows_inserted": inserted,
            "rows_updated": 0,
            "rows_skipped": duplicates,
            "duplicates_count": duplicates,
        }

    @classmethod
    def _import_customers(cls, dataframe: pd.DataFrame) -> dict[str, int]:
        plan = cls._customer_sync_plan(dataframe)
        ERPImportRepository.apply_customer_sync(plan)
        metrics = plan["metrics"]
        return {
            **metrics,
            # Preserve generic audit fields for existing consumers. For a
            # customer master file, rows represent sites.
            "rows_inserted": metrics["customer_sites_inserted"],
            "rows_updated": metrics["customer_sites_updated"],
            "rows_skipped": metrics["customer_sites_unchanged"],
            "duplicates_count": 0,
        }

    @classmethod
    def _import_inventory(
        cls, dataframe: pd.DataFrame, original_filename: str
    ) -> dict[str, int]:
        rows = cls._records(dataframe)
        for row in rows:
            row["archivo_origen"] = original_filename
        inserted, updated = ERPImportRepository.upsert_inventory(rows)
        return {
            "rows_inserted": inserted,
            "rows_updated": updated,
            "rows_skipped": 0,
            "duplicates_count": 0,
        }

    @classmethod
    def _inventory_plan(cls, dataframe: pd.DataFrame) -> dict[str, Any]:
        keys = {
            (
                str(row.fecha_snapshot),
                str(row.idbodega),
                str(row.idproducto),
            )
            for row in dataframe.itertuples()
        }
        existing = ERPImportRepository.existing_inventory_keys(keys)
        warehouse_codes = sorted({
            str(value) for value in dataframe["idbodega"].dropna().unique()
        })
        known = ERPImportRepository.known_inventory_warehouses()
        new_codes = sorted(set(warehouse_codes) - known)
        return {
            "rows_valid": len(dataframe),
            "warehouses_count": len(warehouse_codes),
            "warehouse_codes": warehouse_codes,
            "existing_keys": len(existing),
            "new_warehouses": len(new_codes),
            "new_warehouse_codes": new_codes,
            "total_units": float(dataframe["unidades"].sum()),
            "total_available": float(dataframe["unidades_disponible"].sum()),
            "total_transit": float(dataframe["unidades_transito"].sum()),
            "total_cost_value": float(dataframe["valor_total"].sum()),
        }

    @classmethod
    def _import_fob_prices(
        cls, execution_id: int, dataframe: pd.DataFrame
    ) -> dict[str, int]:
        inserted = ERPImportRepository.insert_fob_prices(
            execution_id, cls._records(dataframe)
        )
        return {
            "rows_inserted": inserted,
            "rows_updated": 0,
            "rows_skipped": 0,
            "duplicates_count": 0,
        }

    @staticmethod
    def _fob_price_plan(dataframe: pd.DataFrame) -> dict[str, Any]:
        return {
            "rows_valid": len(dataframe),
            "products_count": int(dataframe["idproducto"].nunique()),
            "brands_count": int(dataframe["sufijo"].nunique()),
            "suppliers_count": int(dataframe["nit"].nunique()),
            "zero_fob_count": int(dataframe["fob_usd"].eq(0).sum()),
        }

    @classmethod
    def _customer_sync_plan(cls, dataframe: pd.DataFrame) -> dict[str, Any]:
        records = cls._records(dataframe)
        customers: dict[str, dict[str, Any]] = {}
        sites: dict[str, dict[str, Any]] = {}
        for row in records:
            nit = normalize_nit(row.get("nit"))
            row["nit"] = nit
            row["razonsocial"] = str(row.get("razonsocial") or "").strip()
            row["ciudad"] = normalize_site_text(row.get("ciudad"))
            row["direccion1"] = normalize_site_text(
                row.get("direccion1")
            )
            customers.setdefault(nit, {
                "nit": nit, "name": row["razonsocial"],
            })
            row["_sync_site_key"] = customer_site_key(row)
            sites[row["_sync_site_key"]] = row
        return ERPImportRepository.plan_customer_sync(
            list(customers.values()), list(sites.values())
        )

    @classmethod
    def _read(cls, import_type: str, path: Path) -> pd.DataFrame:
        try:
            if import_type == "sales":
                return read_file(path)
            if import_type == "inventory":
                return read_inventory_file(path)
            if path.suffix.lower() == ".csv":
                return pd.read_csv(path)
            return pd.read_excel(path)
        except Exception as error:
            raise ERPImportValidationError(
                f"No fue posible leer el archivo ERP: {error}"
            ) from error

    @classmethod
    def _validate_with_issues(
        cls, import_type: str, dataframe: pd.DataFrame,
        snapshot_date: str | None = None,
    ) -> tuple[
        pd.DataFrame, list[str], list[tuple[str, str]], list[InventoryIssue]
    ]:
        if dataframe.empty:
            raise ERPImportValidationError("El archivo no contiene filas.")
        if import_type == "inventory":
            try:
                result, issues, mapping = normalize_inventory(dataframe)
            except ValueError as error:
                raise ERPImportValidationError(str(error)) from error
            result.insert(0, "fecha_snapshot", snapshot_date)
            warnings = [
                issue.message for issue in issues if issue.severity == "warning"
            ]
            return result, warnings, mapping, issues
        result, header_mapping = cls._normalize_headers(dataframe)
        normalized_names = {canonical for _, canonical in header_mapping}
        required = (
            cls.SALES_REQUIRED if import_type == "sales"
            else cls.FOB_PRICE_REQUIRED if import_type == "fob_prices"
            else cls.CUSTOMER_REQUIRED
        )
        missing = sorted(required - set(normalized_names))
        if missing:
            raise ERPImportValidationError(
                "Faltan columnas obligatorias: " + ", ".join(missing)
            )
        warnings: list[str] = []
        extra = sorted(set(normalized_names) - required)
        if extra:
            warnings.append(
                "El archivo contiene columnas adicionales que serán preservadas "
                "cuando existan en el esquema ERP: " + ", ".join(extra)
            )
        if import_type == "sales":
            result = normalize_raw_sales(result)
            invalid_dates = int(result["fecha"].isna().sum())
            if invalid_dates:
                raise ERPImportValidationError(
                    f"{invalid_dates} filas tienen una fecha de venta inválida."
                )
            return result, warnings, header_mapping, []

        if import_type == "fob_prices":
            return cls._normalize_fob_prices(
                result, warnings, header_mapping
            )

        result["nit"] = result["nit"].map(normalize_nit)
        if result["nit"].eq("").any():
            raise ERPImportValidationError(
                "Todos los clientes deben tener un NIT."
            )
        return result, warnings, header_mapping, []

    @classmethod
    def _normalize_fob_prices(
        cls, dataframe: pd.DataFrame, warnings: list[str],
        header_mapping: list[tuple[str, str]],
    ) -> tuple[
        pd.DataFrame, list[str], list[tuple[str, str]], list[InventoryIssue]
    ]:
        result = dataframe.copy()
        result["_source_row"] = range(2, len(result) + 2)
        issues: list[InventoryIssue] = []

        def text_value(value: Any) -> str:
            if pd.isna(value):
                return ""
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return str(value).strip()

        for column in ("idproducto", "prefijo", "sufijo", "idfam2"):
            result[column] = result[column].map(text_value)
        result["nit"] = result["nit"].map(normalize_nit)

        for column, label in (("fob", "FOB"), ("lista1", "LISTA1")):
            original = result[column]
            cleaned = original.map(
                lambda value: str(value).replace(",", "").strip()
                if pd.notna(value) else ""
            )
            numeric = pd.to_numeric(cleaned, errors="coerce")
            for index in result.index[numeric.isna()]:
                issues.append(InventoryIssue(
                    row_number=int(result.at[index, "_source_row"]),
                    severity="error", code=f"{label}_NO_NUMERICO",
                    message=f"{label} debe contener un valor numérico.",
                    details={"value": text_value(original.at[index])},
                ))
            result[column] = numeric

        required_text = {
            "idproducto": "IDPRODUCTO", "sufijo": "SUFIJO", "nit": "NIT",
        }
        for column, label in required_text.items():
            for index in result.index[result[column].eq("")]:
                issues.append(InventoryIssue(
                    row_number=int(result.at[index, "_source_row"]),
                    severity="error", code=f"{label}_VACIO",
                    message=f"{label} es obligatorio.", details={},
                ))
        for index in result.index[result["fob"].lt(0).fillna(False)]:
            issues.append(InventoryIssue(
                row_number=int(result.at[index, "_source_row"]),
                severity="error", code="FOB_NEGATIVO",
                message="FOB no puede ser negativo.", details={},
            ))
        zero_count = int(result["fob"].eq(0).sum())
        if zero_count:
            warnings.append(
                f"{zero_count} productos tienen FOB igual a cero; "
                "se importarán para conservar el dato del ERP."
            )
            for index in result.index[result["fob"].eq(0)]:
                issues.append(InventoryIssue(
                    row_number=int(result.at[index, "_source_row"]),
                    severity="warning", code="FOB_CERO",
                    message="El producto tiene FOB igual a cero.", details={},
                ))

        duplicate_mask = result.duplicated(
            subset=["idproducto", "nit"], keep=False
        )
        for index in result.index[duplicate_mask]:
            issues.append(InventoryIssue(
                row_number=int(result.at[index, "_source_row"]),
                severity="error", code="PRODUCTO_PROVEEDOR_DUPLICADO",
                message="IDPRODUCTO y NIT están repetidos en el archivo.",
                details={
                    "idproducto": result.at[index, "idproducto"],
                    "nit": result.at[index, "nit"],
                },
            ))

        result = result.rename(columns={"fob": "fob_usd", "lista1": "lista1_cop"})
        result = result.drop(columns=["_source_row"])
        header_mapping = [
            (source, {"fob": "fob_usd", "lista1": "lista1_cop"}.get(canonical, canonical))
            for source, canonical in header_mapping
        ]
        return result, warnings, header_mapping, issues

    @classmethod
    def _validate(
        cls, import_type: str, dataframe: pd.DataFrame,
        snapshot_date: str | None = None,
    ) -> tuple[pd.DataFrame, list[str], list[tuple[str, str]]]:
        """Backward-compatible validation API used by existing callers."""
        result, warnings, mapping, _issues = cls._validate_with_issues(
            import_type, dataframe, snapshot_date
        )
        return result, warnings, mapping

    @staticmethod
    def _normalize_headers(
        dataframe: pd.DataFrame,
    ) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
        mapping: list[tuple[str, str]] = []
        canonical_to_source: dict[str, str] = {}
        rename: dict[Any, str] = {}
        for source in dataframe.columns:
            source_label = str(source)
            canonical = source_label.strip().casefold()
            if not canonical:
                raise ERPImportValidationError(
                    "El archivo contiene un encabezado vacío."
                )
            if canonical in canonical_to_source:
                previous = canonical_to_source[canonical]
                raise ERPImportValidationError(
                    "Encabezados ambiguos: "
                    f"“{previous}” y “{source_label}” representan "
                    f"la misma columna “{canonical}”."
                )
            canonical_to_source[canonical] = source_label
            rename[source] = canonical
            mapping.append((source_label, canonical))
        return dataframe.rename(columns=rename).copy(), mapping

    @staticmethod
    def _records(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        clean = dataframe.astype(object).where(pd.notna(dataframe), None)
        records = clean.to_dict(orient="records")
        for row in records:
            for key, value in tuple(row.items()):
                if isinstance(value, float) and math.isnan(value):
                    row[key] = None
        return records

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _validate_type(import_type: str) -> None:
        if import_type not in {"sales", "customers", "inventory", "fob_prices"}:
            raise ERPImportValidationError("Tipo de importación no válido.")

    @staticmethod
    def _snapshot_date(
        import_type: str, snapshot_date: str | None
    ) -> str | None:
        if import_type != "inventory":
            return None
        value = str(snapshot_date or "").strip()
        if not value:
            raise ERPImportValidationError(
                "La fecha del snapshot es obligatoria."
            )
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as error:
            raise ERPImportValidationError(
                "La fecha del snapshot no es válida."
            ) from error

    @classmethod
    def _preview(
        cls, execution_id: int, import_type: str, filename: str,
        file_hash: str, dataframe: pd.DataFrame, warnings: list[str],
        header_mapping: list[tuple[str, str]],
        sync_metrics: dict[str, Any],
        validation_issues: list[InventoryIssue],
        snapshot_date: str | None,
    ) -> ImportPreview:
        sample = cls._records(dataframe.head(10))
        return ImportPreview(
            execution_id=execution_id,
            import_type=import_type,
            original_filename=filename,
            rows_read=len(dataframe),
            columns=tuple(str(column) for column in dataframe.columns),
            sample_rows=tuple(sample),
            warnings=tuple(warnings),
            file_hash=file_hash,
            header_mapping=tuple(header_mapping),
            sync_metrics=sync_metrics,
            validation_issues=tuple({
                "row_number": issue.row_number,
                "severity": issue.severity,
                "code": issue.code,
                "message": issue.message,
                "details": issue.details,
            } for issue in validation_issues),
            can_confirm=not any(
                issue.severity == "error" for issue in validation_issues
            ),
            snapshot_date=snapshot_date,
        )
