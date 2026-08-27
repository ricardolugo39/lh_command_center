from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import unicodedata

import pandas as pd
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.database.transaction import connection_scope, transaction
from app.storage import upload_path
from app.workspace.constants.opportunity_origin import OpportunityOrigin
from app.workspace.customer_identity import normalize_nit
from app.workspace.repositories.erp_import_repository import ERPImportRepository
from app.workspace.repositories.opportunity_import_repository import (
    OpportunityImportRepository,
)
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.repositories.imported_commercial_line_repository import (
    ImportedCommercialLineRepository,
)
from app.workspace.services.opportunity_import_profile_service import (
    OpportunityImportProfileService,
)
from app.workspace.services.opportunity_identity_resolution_service import (
    OpportunityIdentityResolutionService,
)


class OpportunityImportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class OpportunityImportPreview:
    execution_id: int
    profile_name: str
    profile_version: int
    original_filename: str
    rows_read: int
    groups: tuple[dict[str, Any], ...]
    metrics: dict[str, int]
    can_confirm: bool


class OpportunityImportService:
    """Two-phase, grouped CRM import into the single Opportunity object."""

    SCHEMA_VERSION = "opportunity-import-v1"
    STORAGE_ROOT = upload_path("opportunity-imports")
    ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
    CLOSED_STATUSES = {"won", "lost", "cancelled"}

    @classmethod
    def prepare(
        cls, *, upload: FileStorage, executed_by: str
    ) -> OpportunityImportPreview:
        profile = OpportunityImportProfileService.active_profile()
        if not profile:
            raise OpportunityImportValidationError(
                "No existe un perfil de mapeo activo para oportunidades CRM."
            )
        path, file_hash = cls._store(upload)
        dataframe = cls._read(path, profile)
        groups = cls._attach_pending_state(
            cls._build_groups(dataframe, profile)
        )
        metrics = cls._metrics(groups)
        with transaction():
            execution_id = ERPImportRepository.create_execution({
                "import_type": "crm_opportunities",
                "original_filename": upload.filename,
                "stored_file_path": str(path),
                "file_hash": file_hash,
                "schema_version": cls.SCHEMA_VERSION,
                "status": "previewed",
                "rows_read": len(dataframe),
                "executed_by": executed_by or "system",
                "mapping_profile_version_id": profile["id"],
                **metrics,
                "log": {
                    "phase": "preview",
                    "profile_name": profile["profile_name"],
                    "profile_version": profile["version"],
                    "source_columns": [str(value) for value in dataframe.columns],
                    "groups": groups,
                },
            })
            for group in groups:
                OpportunityImportRepository.upsert_resolution(
                    execution_id,
                    group["external_opportunity_id"],
                    source_customer_key=group.get("customer_identity"),
                    status=group["customer_resolution_status"],
                    customer_id=group.get("customer_id"),
                )
                OpportunityImportRepository.upsert_seller_resolution(
                    execution_id,
                    group["external_opportunity_id"],
                    source_seller=group.get("source_seller"),
                    status=group.get("seller_resolution_status", "matched"),
                    resolved_sales_rep=group.get("resolved_sales_rep"),
                    match_reason=group.get("seller_match_reason"),
                )
            ERPImportRepository.update_execution(execution_id, {
                "customer_resolutions": {
                    group["external_opportunity_id"]: {
                        "status": group["customer_resolution_status"],
                        "customer_id": group.get("customer_id"),
                    }
                    for group in groups
                }
            })
        return cls._preview(execution_id, profile, upload.filename, len(dataframe), groups)

    @classmethod
    def preview(cls, execution_id: int) -> OpportunityImportPreview:
        execution = ERPImportRepository.get_execution(execution_id)
        if not execution or execution["import_type"] != "crm_opportunities":
            raise OpportunityImportValidationError("La importación no existe.")
        log = json.loads(execution.get("execution_log_json") or "{}")
        resolutions = OpportunityImportRepository.resolutions(execution_id)
        groups = cls._apply_resolutions(
            log.get("groups", []), resolutions,
            OpportunityImportRepository.seller_resolutions(execution_id),
        )
        groups = cls._attach_pending_state(groups)
        profile = {
            "profile_name": log.get("profile_name", "Perfil"),
            "version": log.get("profile_version", 0),
        }
        return cls._preview(
            execution_id, profile, execution["original_filename"],
            int(execution["rows_read"]), groups,
        )

    @classmethod
    def resolve_customer(
        cls, execution_id: int, external_id: str, *,
        customer_id: int, resolved_by: str,
    ) -> OpportunityImportPreview:
        execution = ERPImportRepository.get_execution(execution_id)
        if not execution or execution["status"] != "previewed":
            raise OpportunityImportValidationError(
                "Esta importación ya no admite resoluciones."
            )
        with connection_scope() as connection:
            customer = connection.execute(
                "SELECT id FROM ws_customers WHERE id=?", (customer_id,)
            ).fetchone()
        if not customer:
            raise OpportunityImportValidationError("El cliente seleccionado no existe.")
        resolutions = OpportunityImportRepository.resolutions(execution_id)
        resolution = resolutions.get(str(external_id))
        if not resolution:
            raise OpportunityImportValidationError(
                "La oportunidad no pertenece a esta importación."
            )
        if resolution["resolution_status"] != "needs_review":
            raise OpportunityImportValidationError(
                "Este registro no requiere resolución manual de cliente."
            )
        with transaction():
            OpportunityImportRepository.upsert_resolution(
                execution_id, str(external_id),
                source_customer_key=resolution.get("source_customer_key"),
                status="resolved_by_user", customer_id=customer_id,
                resolved_by=resolved_by or "system",
            )
            normalized_identity = (
                OpportunityIdentityResolutionService.normalize_company(
                    resolution.get("source_customer_key")
                )
            )
            if normalized_identity:
                OpportunityImportRepository.save_customer_alias(
                    normalized_identity,
                    resolution.get("source_customer_key") or normalized_identity,
                    customer_id,
                    confirmed_by=resolved_by or "system",
                )
            ERPImportRepository.update_execution(execution_id, {
                "customer_resolutions": {
                    key: {
                        "status": (
                            "resolved_by_user" if key == str(external_id)
                            else value["resolution_status"]
                        ),
                        "customer_id": (
                            customer_id if key == str(external_id)
                            else value.get("customer_id")
                        ),
                    }
                    for key, value in resolutions.items()
                }
            })
        return cls.preview(execution_id)

    @classmethod
    def resolve_seller(
        cls, execution_id: int, external_id: str, *,
        sales_rep: str, resolved_by: str,
    ) -> OpportunityImportPreview:
        execution = ERPImportRepository.get_execution(execution_id)
        if not execution or execution["status"] != "previewed":
            raise OpportunityImportValidationError(
                "Esta importación ya no admite resoluciones."
            )
        clean_sales_rep = str(sales_rep or "").strip()
        candidates = OpportunityImportRepository.seller_candidates()
        if clean_sales_rep not in candidates:
            raise OpportunityImportValidationError(
                "El vendedor seleccionado no existe en la estructura comercial."
            )
        resolutions = OpportunityImportRepository.seller_resolutions(execution_id)
        resolution = resolutions.get(str(external_id))
        if not resolution:
            raise OpportunityImportValidationError(
                "La oportunidad no pertenece a esta importación."
            )
        with transaction():
            OpportunityImportRepository.upsert_seller_resolution(
                execution_id, str(external_id),
                source_seller=resolution.get("source_seller"),
                status="resolved_by_user",
                resolved_sales_rep=clean_sales_rep,
                match_reason="user_confirmed",
                resolved_by=resolved_by or "system",
            )
            normalized = OpportunityIdentityResolutionService.normalize_text(
                resolution.get("source_seller")
            )
            if normalized:
                OpportunityImportRepository.save_seller_alias(
                    normalized, resolution.get("source_seller") or normalized,
                    clean_sales_rep, confirmed_by=resolved_by or "system",
                )
        return cls.preview(execution_id)

    @staticmethod
    def pending_queue() -> list[dict[str, Any]]:
        return OpportunityImportRepository.list_pending()

    @classmethod
    def resolve_pending_customer(
        cls, pending_id: int, *, customer_id: int,
        apply_to_company: bool, resolved_by: str,
    ) -> int:
        pending = OpportunityImportRepository.get_pending(pending_id)
        if not pending or pending["resolution_status"] == "imported":
            raise OpportunityImportValidationError(
                "La oportunidad pendiente no existe o ya fue importada."
            )
        with connection_scope() as connection:
            customer = connection.execute(
                "SELECT id FROM ws_customers WHERE id=?", (customer_id,)
            ).fetchone()
        if not customer:
            raise OpportunityImportValidationError(
                "El cliente seleccionado no existe."
            )
        normalized = str(pending["normalized_customer_identity"] or "")
        pending_ids = (
            OpportunityImportRepository.pending_ids_for_identity(normalized)
            if apply_to_company and normalized else [pending_id]
        )
        with transaction():
            alias_created = bool(normalized)
            if alias_created:
                OpportunityImportRepository.save_customer_alias(
                    normalized,
                    pending["source_company_name"] or normalized,
                    customer_id,
                    confirmed_by=resolved_by or "system",
                )
            return OpportunityImportRepository.resolve_pending(
                pending_ids, customer_id=customer_id,
                actor=resolved_by or "system",
                alias_created=alias_created,
            )

    @classmethod
    def import_resolved_pending(
        cls, *, pending_ids: list[int] | None, executed_by: str
    ) -> dict[str, Any]:
        ready = OpportunityImportRepository.list_pending(
            statuses=("ready",)
        )
        if pending_ids is not None:
            selected = set(pending_ids)
            ready = [item for item in ready if int(item["id"]) in selected]
        if not ready:
            raise OpportunityImportValidationError(
                "No hay oportunidades resueltas listas para importar."
            )
        by_execution: dict[int, list[dict[str, Any]]] = {}
        for item in ready:
            by_execution.setdefault(
                int(item["latest_import_execution_id"]), []
            ).append(item)

        totals = {
            "created": 0, "updated": 0, "unchanged": 0,
            "execution_ids": [],
        }
        for source_execution_id, items in by_execution.items():
            source_execution = ERPImportRepository.get_execution(
                source_execution_id
            )
            if not source_execution:
                raise OpportunityImportValidationError(
                    "No se encontró la ejecución fuente retenida."
                )
            path = Path(source_execution["stored_file_path"])
            if cls._hash(path) != source_execution["file_hash"]:
                raise OpportunityImportValidationError(
                    "El archivo retenido cambió y no puede reutilizarse."
                )
            profile_id = int(items[0]["mapping_profile_version_id"])
            profile = OpportunityImportRepository.profile_version(profile_id)
            if not profile:
                raise OpportunityImportValidationError(
                    "No se encontró la versión inmutable del perfil."
                )
            groups = cls._build_groups(cls._read(path, profile), profile)
            by_external = {
                str(group["external_opportunity_id"]): group
                for group in groups
            }
            with transaction():
                execution_id = ERPImportRepository.create_execution({
                    "import_type": "crm_opportunities",
                    "original_filename": source_execution["original_filename"],
                    "stored_file_path": str(path),
                    "file_hash": source_execution["file_hash"],
                    "schema_version": cls.SCHEMA_VERSION,
                    "status": "processing",
                    "rows_read": source_execution["rows_read"],
                    "executed_by": executed_by or "system",
                    "mapping_profile_version_id": profile_id,
                    "groups_identified": len(items),
                    "groups_eligible": len(items),
                    "log": {
                        "phase": "resolved_pending_import",
                        "original_source_execution_id": source_execution_id,
                        "pending_ids": [item["id"] for item in items],
                    },
                })
                created = updated = unchanged = 0
                created_ids: list[int] = []
                updated_ids: list[int] = []
                now = datetime.now(timezone.utc).isoformat()
                owned_fields = cls._owned_fields(profile)
                for item in items:
                    group = by_external.get(
                        str(item["external_opportunity_id"])
                    )
                    if not group:
                        raise OpportunityImportValidationError(
                            "La oportunidad ya no existe en el archivo retenido."
                        )
                    if group["action"] == "blocked":
                        raise OpportunityImportValidationError(
                            "La oportunidad resuelta tiene un conflicto "
                            "de ciclo de vida que impide importarla."
                        )
                    with connection_scope() as connection:
                        customer = connection.execute(
                            "SELECT id FROM ws_customers WHERE id=?",
                            (item["customer_id"],),
                        ).fetchone()
                    if not customer:
                        raise OpportunityImportValidationError(
                            "El cliente resuelto ya no existe."
                        )
                    group["customer_id"] = int(item["customer_id"])
                    group["customer_resolution_status"] = "resolved_by_user"
                    existing = ProjectRepository.find_by_origin_external_id(
                        OpportunityOrigin.CRM,
                        group["external_opportunity_id"],
                    )
                    canonical = group["canonical"]
                    metadata = json.dumps({
                        "source_facts": canonical,
                        "source_rows": group["source_rows"],
                        "source_row_numbers": group["source_row_numbers"],
                        "source_row_ids": group.get("source_row_ids", []),
                        "product_lines": group.get("product_lines", []),
                        "origin_references": group.get("origin_references", []),
                        "profile_version_id": profile_id,
                        "original_source_execution_id": source_execution_id,
                    }, ensure_ascii=False, default=str)
                    if not existing:
                        opportunity_id = ProjectRepository.create_project(
                            customer_id=int(item["customer_id"]),
                            name=str(canonical["opportunity_name"]),
                            objective=str(
                                canonical.get("objective")
                                or canonical["opportunity_name"]
                            ),
                            status=cls._safe_open_status(
                                canonical.get("stage")
                            ),
                            sales_rep=group.get("resolved_sales_rep"),
                            origin=OpportunityOrigin.CRM,
                            external_id=group["external_opportunity_id"],
                            origin_reference=group.get("origin_reference")
                            or group["external_opportunity_id"],
                            imported_at=now,
                            created_import_execution_id=execution_id,
                            last_import_execution_id=execution_id,
                            import_metadata=metadata,
                        )
                        created += 1
                        created_ids.append(opportunity_id)
                    else:
                        action = cls._action(existing, canonical, profile)
                        opportunity_id = int(existing["id"])
                        if action == "unchanged":
                            ProjectRepository.update_synchronization_audit(
                                opportunity_id, last_synchronized_at=now,
                                last_import_execution_id=execution_id,
                                import_metadata=metadata,
                            )
                            unchanged += 1
                        else:
                            candidates = {
                                "sales_rep": group.get("resolved_sales_rep"),
                            }
                            values = {
                                key: value
                                for key, value in candidates.items()
                                if key in owned_fields and value is not None
                            }
                            ProjectRepository.synchronize_imported_fields(
                                opportunity_id, values,
                                last_synchronized_at=now,
                                last_import_execution_id=execution_id,
                                import_metadata=metadata,
                            )
                            updated += 1
                            updated_ids.append(opportunity_id)
                    if group.get("product_lines"):
                        ImportedCommercialLineRepository.synchronize(
                            opportunity_id,
                            external_opportunity_id=group[
                                "external_opportunity_id"
                            ],
                            origin_reference=group.get("origin_reference"),
                            product_lines=group["product_lines"],
                            import_execution_id=execution_id,
                        )
                    OpportunityImportRepository.mark_pending_imported(
                        int(item["id"]), opportunity_id=opportunity_id,
                        import_execution_id=execution_id,
                        actor=executed_by or "system",
                    )
                metrics = {
                    "rows_inserted": created, "rows_updated": updated,
                    "rows_skipped": unchanged,
                    "groups_eligible": len(items),
                    "groups_imported": created + updated,
                    "groups_deferred": 0,
                }
                ERPImportRepository.update_execution(execution_id, {
                    "status": "completed", **metrics,
                    "completed_at": ERPImportRepository.completed_at(),
                    "log": {
                        "phase": "resolved_pending_completed",
                        "original_source_execution_id": source_execution_id,
                        "created_opportunity_ids": created_ids,
                        "updated_opportunity_ids": updated_ids,
                        "metrics": metrics,
                    },
                })
                totals["created"] += created
                totals["updated"] += updated
                totals["unchanged"] += unchanged
                totals["execution_ids"].append(execution_id)
        return totals

    @classmethod
    def confirm(
        cls, execution_id: int, *, confirmed: bool, executed_by: str
    ) -> dict[str, Any]:
        if not confirmed:
            raise OpportunityImportValidationError(
                "Debe confirmar explícitamente la importación."
            )
        execution = ERPImportRepository.get_execution(execution_id)
        if not execution or execution["status"] != "previewed":
            raise OpportunityImportValidationError(
                "Esta importación ya fue procesada o no puede confirmarse."
            )
        profile = OpportunityImportRepository.active_version()
        if not profile or profile["id"] != execution["mapping_profile_version_id"]:
            raise OpportunityImportValidationError(
                "El perfil activo cambió. Genere una nueva vista previa."
            )
        path = Path(execution["stored_file_path"])
        if cls._hash(path) != execution["file_hash"]:
            raise OpportunityImportValidationError(
                "El archivo cambió después de la vista previa."
            )
        groups = cls._build_groups(cls._read(path, profile), profile)
        resolutions = OpportunityImportRepository.resolutions(execution_id)
        groups = cls._apply_resolutions(
            groups, resolutions,
            OpportunityImportRepository.seller_resolutions(execution_id),
        )
        groups = cls._attach_pending_state(groups)
        eligible = [
            group for group in groups
            if group["customer_resolution_status"] in {
                "matched", "resolved_by_user"
            } and group["action"] != "blocked"
        ]
        deferred = [group for group in groups if group not in eligible]

        created = updated = unchanged = 0
        created_ids: list[int] = []
        updated_ids: list[int] = []
        now = datetime.now(timezone.utc).isoformat()
        try:
            with transaction():
                ERPImportRepository.update_execution(
                    execution_id, {"status": "processing"}
                )
                owned_fields = cls._owned_fields(profile)
                for group in eligible:
                    canonical = group["canonical"]
                    existing = ProjectRepository.find_by_origin_external_id(
                        OpportunityOrigin.CRM,
                        group["external_opportunity_id"],
                    )
                    metadata = json.dumps({
                        "source_facts": canonical,
                        "source_rows": group["source_rows"],
                        "source_row_numbers": group["source_row_numbers"],
                        "source_row_ids": group.get("source_row_ids", []),
                        "product_lines": group.get("product_lines", []),
                        "origin_references": group.get("origin_references", []),
                        "group_warnings": group.get("warnings", []),
                        "profile_version_id": profile["id"],
                    }, ensure_ascii=False, default=str)
                    if not existing:
                        created_id = ProjectRepository.create_project(
                            customer_id=int(group["customer_id"]),
                            name=str(canonical["opportunity_name"]),
                            objective=str(
                                canonical.get("objective")
                                or canonical["opportunity_name"]
                            ),
                            status=cls._safe_open_status(canonical.get("stage")),
                            sales_rep=group.get("resolved_sales_rep"),
                            origin=OpportunityOrigin.CRM,
                            external_id=group["external_opportunity_id"],
                            origin_reference=canonical.get("origin_reference")
                            or group["external_opportunity_id"],
                            imported_at=now,
                            created_import_execution_id=execution_id,
                            last_import_execution_id=execution_id,
                            import_metadata=metadata,
                        )
                        created_ids.append(created_id)
                        opportunity_id = created_id
                        created += 1
                    elif group["action"] == "unchanged":
                        ProjectRepository.update_synchronization_audit(
                            existing["id"], last_synchronized_at=now,
                            last_import_execution_id=execution_id,
                            import_metadata=metadata,
                        )
                        opportunity_id = int(existing["id"])
                        unchanged += 1
                    else:
                        candidates = {
                            "name": canonical.get("opportunity_name"),
                            "objective": canonical.get("objective"),
                            "sales_rep": group.get("resolved_sales_rep"),
                            "status": cls._safe_open_status(canonical.get("stage")),
                        }
                        values = {
                            key: value for key, value in candidates.items()
                            if key in owned_fields and value is not None
                        }
                        ProjectRepository.synchronize_imported_fields(
                            existing["id"], values,
                            last_synchronized_at=now,
                            last_import_execution_id=execution_id,
                            import_metadata=metadata,
                        )
                        updated_ids.append(int(existing["id"]))
                        opportunity_id = int(existing["id"])
                        updated += 1
                    if group.get("pending_id"):
                        OpportunityImportRepository.mark_pending_imported(
                            int(group["pending_id"]),
                            opportunity_id=opportunity_id,
                            import_execution_id=execution_id,
                            actor=executed_by or "system",
                        )
                    if group.get("product_lines"):
                        ImportedCommercialLineRepository.synchronize(
                            opportunity_id,
                            external_opportunity_id=group[
                                "external_opportunity_id"
                            ],
                            origin_reference=group.get("origin_reference"),
                            product_lines=group["product_lines"],
                            import_execution_id=execution_id,
                        )
                for group in deferred:
                    OpportunityImportRepository.upsert_pending(
                        group,
                        execution_id=execution_id,
                        profile_version_id=profile["id"],
                        actor=executed_by or "system",
                    )
                final_metrics = {
                    "rows_inserted": created, "rows_updated": updated,
                    "rows_skipped": unchanged,
                    "groups_to_create": created,
                    "groups_to_update": updated,
                    "groups_unchanged": unchanged,
                    "groups_eligible": len(eligible),
                    "groups_imported": created + updated,
                    "groups_deferred": len(deferred),
                    "groups_needs_review": sum(
                        group["action"] == "needs_review"
                        for group in deferred
                    ),
                    "groups_blocked": sum(
                        group["action"] == "blocked"
                        for group in deferred
                    ),
                }
                ERPImportRepository.update_execution(execution_id, {
                    "status": "completed", **final_metrics,
                    "completed_at": ERPImportRepository.completed_at(),
                    "log": {
                        "phase": "completed",
                        "confirmed_by": executed_by or "system",
                        "metrics": final_metrics,
                        "created_opportunity_ids": created_ids,
                        "updated_opportunity_ids": updated_ids,
                        "deferred_external_ids": [
                            group["external_opportunity_id"]
                            for group in deferred
                        ],
                        "blocked_external_ids": [
                            group["external_opportunity_id"]
                            for group in deferred
                            if group["action"] == "blocked"
                        ],
                    },
                })
        except Exception as error:
            with transaction():
                ERPImportRepository.update_execution(execution_id, {
                    "status": "failed", "errors": [str(error)],
                    "completed_at": ERPImportRepository.completed_at(),
                    "log": {"phase": "failed", "error": str(error)},
                })
            raise
        return ERPImportRepository.get_execution(execution_id) or {}

    @classmethod
    def _build_groups(
        cls, dataframe: pd.DataFrame, profile: dict[str, Any]
    ) -> list[dict[str, Any]]:
        mapping = profile["column_mapping"]
        missing_headers = sorted(set(mapping.values()) - set(dataframe.columns))
        if missing_headers:
            raise OpportunityImportValidationError(
                "El archivo no contiene las columnas configuradas: "
                + ", ".join(missing_headers)
            )
        canonical_rows: list[tuple[int, dict[str, Any]]] = []
        transformations = profile.get("transformation_rules", {})
        for index, row in dataframe.iterrows():
            item = {}
            for concept, header in mapping.items():
                value = row[header]
                if pd.isna(value):
                    value = None
                item[concept] = OpportunityImportProfileService.transform(
                    value, transformations.get(concept)
                )
            canonical_rows.append((int(index) + 2, item))

        buckets: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for row_number, row in canonical_rows:
            external_id = str(row.get("external_opportunity_id") or "").strip()
            if not external_id:
                external_id = f"__missing_row_{len(buckets) + 1}"
            buckets.setdefault(external_id, []).append((row_number, row))

        groups: list[dict[str, Any]] = []
        production_strategy = (
            profile.get("grouping_configuration", {}).get("strategy")
            == "production_crm_product_lines_v1"
        )
        production_customer_index = (
            OpportunityIdentityResolutionService._customer_index()
            if production_strategy else None
        )
        production_seller_index = (
            OpportunityIdentityResolutionService._seller_index()
            if production_strategy else None
        )
        existing_by_external_id = ProjectRepository.list_by_origin(
            OpportunityOrigin.CRM
        )
        consistency = profile.get("grouping_configuration", {}).get(
            "consistent_concepts",
            ["customer_identity", "opportunity_name"],
        )
        for external_id, numbered_rows in buckets.items():
            rows = [row for _number, row in numbered_rows]
            canonical = dict(rows[0])
            production = production_strategy
            production_summary = (
                cls._aggregate_production(
                    numbered_rows,
                    customer_index=production_customer_index,
                )
                if production else {}
            )
            canonical.update(production_summary.get("canonical", {}))
            conflicts = [
                concept for concept in consistency
                if len({
                    (
                        OpportunityIdentityResolutionService.normalize_company(
                            row.get(concept)
                        )
                        if production and concept == "customer_identity"
                        else OpportunityIdentityResolutionService.normalize_text(
                            row.get(concept)
                        )
                        if production and concept == "seller"
                        else str(row.get(concept) or "").strip()
                    )
                    for row in rows
                    if row.get(concept) not in (None, "")
                }) > 1
            ]
            customer_key = str(canonical.get("customer_identity") or "").strip()
            if production:
                customer_resolution = (
                    OpportunityIdentityResolutionService.resolve_customer(
                        company_name=canonical.get("customer_identity"),
                        city=canonical.get("customer_city"),
                        phone=canonical.get("customer_phone"),
                        mobile=canonical.get("customer_mobile"),
                        customer_index=production_summary["customer_index"],
                    )
                )
                seller_resolution = (
                    OpportunityIdentityResolutionService.resolve_seller(
                        canonical.get("seller"),
                        seller_index=production_seller_index,
                    )
                )
                customer_id = customer_resolution["customer_id"]
            else:
                customer_id = cls._match_customer(customer_key)
                customer_resolution = {
                    "status": "matched" if customer_id else "needs_review",
                    "reason": "stable_erp_customer_id" if customer_id else "not_found",
                    "candidates": [], "matched_customer_name": None,
                }
                seller_resolution = {
                    "status": "matched",
                    "resolved_sales_rep": canonical.get("seller"),
                    "reason": "source_value", "candidates": [],
                }
            existing = existing_by_external_id.get(external_id)
            blocked_reason = None
            if external_id.startswith("__missing_row_"):
                blocked_reason = "Falta el identificador externo."
            elif "customer_identity" in conflicts:
                blocked_reason = (
                    "Valores inconsistentes dentro del grupo: "
                    + ", ".join(conflicts)
                )
            elif customer_resolution["status"] == "blocked":
                blocked_reason = (
                    "No existe un nombre de empresa que permita resolver "
                    "el cliente de forma segura."
                )
            elif existing and existing.get("status") in cls.CLOSED_STATUSES:
                mapped = cls._safe_open_status(canonical.get("stage"))
                if mapped != existing.get("status"):
                    blocked_reason = (
                        "La oportunidad está cerrada y su ciclo de vida está protegido."
                    )
            resolution_status = (
                "blocked" if blocked_reason
                else customer_resolution["status"]
            )
            action = (
                "blocked" if blocked_reason
                else "needs_review" if customer_id is None
                else cls._action(existing, canonical, profile)
            )
            groups.append({
                "origin": OpportunityOrigin.CRM,
                "external_opportunity_id": external_id,
                "origin_reference": canonical.get("origin_reference") or external_id,
                "origin_references": production_summary.get(
                    "origin_references",
                    [canonical.get("origin_reference")] if canonical.get("origin_reference") else [],
                ),
                "customer_identity": customer_key,
                "normalized_customer_identity": (
                    OpportunityIdentityResolutionService.normalize_company(
                        customer_key
                    )
                ),
                "customer_id": customer_id,
                "customer_resolution_status": resolution_status,
                "customer_match_reason": customer_resolution["reason"],
                "customer_match_candidates": customer_resolution["candidates"],
                "matched_customer_name": customer_resolution.get(
                    "matched_customer_name"
                ),
                "source_seller": canonical.get("seller"),
                "resolved_sales_rep": seller_resolution["resolved_sales_rep"],
                "seller_resolution_status": seller_resolution["status"],
                "seller_match_reason": seller_resolution["reason"],
                "seller_match_candidates": seller_resolution["candidates"],
                "action": action,
                "blocked_reason": blocked_reason,
                "source_rows": len(rows),
                "source_row_numbers": [
                    number for number, _row in numbered_rows
                ],
                "source_row_ids": production_summary.get("source_row_ids", []),
                "product_lines": production_summary.get("product_lines", []),
                "product_line_count": production_summary.get(
                    "product_line_count", len(rows)
                ),
                "brands": production_summary.get("brands", []),
                "total_potential_value": canonical.get("potential_value"),
                "canonical": canonical,
                "existing_opportunity_id": existing["id"] if existing else None,
                "field_changes": cls._field_changes(existing, canonical, profile),
                "protected_local_fields": [
                    "commercial_amount", "commercial_currency", "initiative_id",
                    "activities", "followups", "quotes", "files", "visits",
                    "rfqs", "commercial_approvals", "timeline", "closure",
                ],
                "conflicts": (
                    ([blocked_reason] if blocked_reason else [])
                    + production_summary.get("conflicts", [])
                ),
                "warnings": production_summary.get("warnings", []) + (
                    ["El vendedor requiere revisión."]
                    if seller_resolution["status"] == "needs_review" else []
                ),
                "errors": [blocked_reason] if blocked_reason else [],
            })
        return groups

    @classmethod
    def _aggregate_production(
        cls, numbered_rows: list[tuple[int, dict[str, Any]]], *,
        customer_index: dict[str, Any],
    ) -> dict[str, Any]:
        rows = [row for _number, row in numbered_rows]
        unique_rows: list[dict[str, Any]] = []
        row_numbers_by_fingerprint: dict[str, int] = {}
        seen: set[str] = set()
        for row_number, row in numbered_rows:
            fingerprint = json.dumps(row, sort_keys=True, default=str)
            if fingerprint not in seen:
                seen.add(fingerprint)
                unique_rows.append(row)
                row_numbers_by_fingerprint[fingerprint] = row_number

        latest_date = max(
            (str(row.get("source_updated_at") or "") for row in unique_rows),
            default="",
        )
        latest = [
            row for row in unique_rows
            if str(row.get("source_updated_at") or "") == latest_date
        ] or unique_rows
        warnings: list[str] = []
        conflicts: list[str] = []
        canonical = dict(unique_rows[0])
        for concept in (
            "customer_identity", "customer_site", "customer_phone",
            "customer_mobile", "customer_city", "seller", "creator",
        ):
            canonical[concept] = next(
                (
                    row.get(concept) for row in latest
                    if row.get(concept) not in (None, "")
                ),
                next(
                    (
                        row.get(concept) for row in unique_rows
                        if row.get(concept) not in (None, "")
                    ),
                    None,
                ),
            )
        latest_concepts = (
            "crm_status", "crm_stage", "priority", "probability",
            "close_date", "source_updated_at",
        )
        for concept in latest_concepts:
            values = sorted({
                str(row.get(concept)).strip()
                for row in latest if row.get(concept) not in (None, "")
            })
            if values:
                canonical[concept] = latest[0].get(concept)
            all_values = {
                str(row.get(concept)).strip()
                for row in unique_rows if row.get(concept) not in (None, "")
            }
            if len(all_values) > 1:
                warnings.append(
                    f"{concept}: se tomó el registro CRM más reciente."
                )
            if len(values) > 1:
                conflicts.append(
                    f"{concept}: valores distintos en registros de la misma fecha."
                )

        line_fields = (
            "source_row_id", "brand", "product_code",
            "product_description", "line_potential_value",
        )
        product_lines = []
        occurrences: dict[str, int] = {}
        for row in unique_rows:
            if not any(
                row.get(field) not in (None, "")
                for field in line_fields[1:]
            ):
                continue
            line = {field: row.get(field) for field in line_fields}
            fingerprint = json.dumps(row, sort_keys=True, default=str)
            line["source_row_number"] = row_numbers_by_fingerprint[fingerprint]
            identity = "|".join(
                str(row.get(field) or "").strip().upper()
                for field in (
                    "source_row_id", "brand", "product_code",
                    "product_description",
                )
            )
            occurrence = occurrences.get(identity, 0) + 1
            occurrences[identity] = occurrence
            line["source_line_key"] = hashlib.sha256(
                f"{identity}|{occurrence}".encode()
            ).hexdigest()
            product_lines.append(line)
        values = [
            float(line["line_potential_value"])
            for line in product_lines
            if line.get("line_potential_value") is not None
        ]
        canonical["potential_value"] = sum(values)
        brands = sorted({
            str(line["brand"]).strip() for line in product_lines
            if line.get("brand")
        })
        references = sorted({
            str(row["origin_reference"]).strip() for row in unique_rows
            if row.get("origin_reference")
        })
        canonical["origin_reference"] = (
            next(
                (
                    str(row["origin_reference"]).strip()
                    for row in latest if row.get("origin_reference")
                ),
                references[0] if references else None,
            )
        )
        canonical["opportunity_name"] = cls._production_name(
            canonical, product_lines, brands
        )
        canonical["stage"] = cls._map_crm_lifecycle(
            canonical.get("crm_status"), canonical.get("crm_stage")
        )
        canonical["product_lines"] = product_lines
        canonical["brands"] = brands
        if canonical.get("crm_status") in {"Realizado", "Cancelado"}:
            warnings.append(
                "El estado CRM se usará para clasificar el ciclo de vida "
                "y se conservará como evidencia de origen."
            )
        if len(unique_rows) != len(rows):
            warnings.append(
                f"Se excluyeron {len(rows) - len(unique_rows)} filas "
                "exactamente duplicadas del valor potencial."
            )
        return {
            "canonical": canonical,
            "customer_index": customer_index,
            "origin_references": references,
            "source_row_ids": sorted({
                str(row["source_row_id"]).strip() for row in unique_rows
                if row.get("source_row_id")
            }),
            "product_lines": product_lines,
            "product_line_count": len(product_lines),
            "brands": brands,
            "warnings": warnings,
            "conflicts": conflicts,
        }

    @staticmethod
    def _production_name(
        canonical: dict[str, Any], product_lines: list[dict[str, Any]],
        brands: list[str],
    ) -> str:
        brand_label = " / ".join(brands[:3])
        code = next(
            (
                str(line["product_code"]).strip()
                for line in product_lines if line.get("product_code")
            ),
            "",
        )
        description = next(
            (
                str(line["product_description"]).strip()
                for line in product_lines if line.get("product_description")
            ),
            "",
        )
        evidence = code or description[:42].strip()
        if brand_label and evidence:
            return f"{brand_label} · {evidence}"[:100]
        if brand_label:
            return brand_label[:100]
        reference = str(canonical.get("origin_reference") or "").strip()
        if reference:
            return f"Oportunidad CRM · {reference}"[:100]
        return (
            f"Oportunidad CRM {canonical.get('external_opportunity_id')}"
        )[:100]

    @classmethod
    def _action(
        cls, existing: dict[str, Any] | None,
        canonical: dict[str, Any], profile: dict[str, Any],
    ) -> str:
        if not existing:
            return "create"
        field_map = {
            "name": "opportunity_name", "objective": "objective",
            "sales_rep": "seller", "status": "stage",
        }
        owned = cls._owned_fields(profile)
        for field in owned:
            concept = field_map.get(field)
            if concept and canonical.get(concept) is not None:
                target = (
                    cls._safe_open_status(canonical[concept])
                    if field == "status" else canonical[concept]
                )
                if str(existing.get(field) or "") != str(target or ""):
                    return "update"
        try:
            previous = json.loads(existing.get("import_metadata") or "{}")
        except (TypeError, json.JSONDecodeError):
            previous = {}
        if previous.get("source_facts") != canonical:
            return "update"
        return "unchanged"

    @classmethod
    def _field_changes(
        cls, existing: dict[str, Any] | None,
        canonical: dict[str, Any], profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not existing:
            return []
        field_map = {
            "name": "opportunity_name", "objective": "objective",
            "sales_rep": "seller", "status": "stage",
        }
        owned = cls._owned_fields(profile)
        changes = []
        for field in sorted(owned):
            concept = field_map.get(field)
            if not concept or canonical.get(concept) is None:
                continue
            proposed = (
                cls._safe_open_status(canonical[concept])
                if field == "status" else canonical[concept]
            )
            if str(existing.get(field) or "") != str(proposed or ""):
                changes.append({
                    "field": field, "current": existing.get(field),
                    "proposed": proposed,
                })
        return changes

    @staticmethod
    def _safe_open_status(stage: Any) -> str:
        value = str(stage or "prospect").strip().lower()
        return value if value in {
            "prospect", "quoting", "waiting_customer", "negotiation",
            "won", "lost", "cancelled",
        } else "prospect"

    @classmethod
    def _owned_fields(cls, profile: dict[str, Any]) -> set[str]:
        owned = set(
            profile.get("ownership_configuration", {}).get(
                "import_owned_fields", []
            )
        )
        if (
            profile.get("grouping_configuration", {}).get("strategy")
            == "production_crm_product_lines_v1"
        ):
            owned.add("status")
        return owned

    @staticmethod
    def _normalized_lifecycle(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        return " ".join(
            "".join(char for char in text if not unicodedata.combining(char))
            .casefold().replace("_", "-").split()
        )

    @classmethod
    def _map_crm_lifecycle(cls, crm_status: Any, crm_stage: Any) -> str:
        status = cls._normalized_lifecycle(crm_status)
        stage = cls._normalized_lifecycle(crm_stage)
        if status in {"cancelado", "cancelada", "cancelled"}:
            return "cancelled"
        if status in {"realizado", "realizada", "ganado", "ganada", "won"}:
            return "won"
        if status in {"perdido", "perdida", "lost"}:
            return "lost"
        if "negoci" in stage:
            return "negotiation"
        if "esper" in stage and "cliente" in stage:
            return "waiting_customer"
        if "propuesta" in stage or "cotiz" in stage:
            return "quoting"
        return "prospect"

    @staticmethod
    def _match_customer(customer_key: str) -> int | None:
        normalized = normalize_nit(customer_key)
        if not normalized:
            return None
        with connection_scope() as connection:
            rows = connection.execute(
                "SELECT id, erp_customer_id FROM ws_customers "
                "WHERE erp_customer_id IS NOT NULL"
            ).fetchall()
        matches = [
            int(row["id"]) for row in rows
            if normalize_nit(row["erp_customer_id"]) == normalized
        ]
        return matches[0] if len(matches) == 1 else None

    @classmethod
    def _apply_resolutions(
        cls, groups: list[dict[str, Any]],
        resolutions: dict[str, dict[str, Any]],
        seller_resolutions: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        result = []
        for source in groups:
            group = dict(source)
            resolution = resolutions.get(str(group["external_opportunity_id"]))
            if resolution and resolution.get("resolution_status") == "resolved_by_user":
                group["customer_id"] = resolution["customer_id"]
                group["customer_resolution_status"] = "resolved_by_user"
                if group["action"] == "needs_review":
                    group["action"] = (
                        "update" if group.get("existing_opportunity_id") else "create"
                    )
            seller = (seller_resolutions or {}).get(
                str(group["external_opportunity_id"])
            )
            if seller and seller.get("resolution_status") == "resolved_by_user":
                group["resolved_sales_rep"] = seller["resolved_sales_rep"]
                group["seller_resolution_status"] = "resolved_by_user"
                group["seller_match_reason"] = "user_confirmed"
                if (
                    group.get("existing_opportunity_id")
                    and group.get("action") == "unchanged"
                ):
                    group["action"] = "update"
            result.append(group)
        return result

    @classmethod
    def _attach_pending_state(
        cls, groups: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        pending = {
            str(item["external_opportunity_id"]): item
            for item in OpportunityImportRepository.list_pending()
        }
        result = []
        for source in groups:
            group = dict(source)
            item = pending.get(str(group["external_opportunity_id"]))
            if item:
                group["pending_id"] = int(item["id"])
                if (
                    item["resolution_status"] == "ready"
                    and item["customer_id"] is not None
                ):
                    group["customer_id"] = int(item["customer_id"])
                    group["customer_resolution_status"] = "resolved_by_user"
                    group["customer_match_reason"] = "pending_user_resolution"
                    if group["action"] in {"needs_review", "blocked"}:
                        group["action"] = (
                            "update"
                            if group.get("existing_opportunity_id")
                            else "create"
                        )
                        group["blocked_reason"] = None
            result.append(group)
        return result

    @classmethod
    def _preview(
        cls, execution_id: int, profile: dict[str, Any],
        filename: str, rows_read: int, groups: list[dict[str, Any]],
    ) -> OpportunityImportPreview:
        metrics = cls._metrics(groups)
        return OpportunityImportPreview(
            execution_id=execution_id,
            profile_name=profile["profile_name"],
            profile_version=int(profile["version"]),
            original_filename=filename,
            rows_read=rows_read,
            groups=tuple(groups),
            metrics=metrics,
            can_confirm=any(
                group["customer_resolution_status"] in {
                    "matched", "resolved_by_user"
                } and group["action"] != "blocked"
                for group in groups
            ),
        )

    @staticmethod
    def _metrics(groups: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "groups_identified": len(groups),
            "groups_eligible": sum(
                g["customer_resolution_status"] in {
                    "matched", "resolved_by_user"
                } and g["action"] != "blocked"
                for g in groups
            ),
            "groups_to_create": sum(g["action"] == "create" for g in groups),
            "groups_to_update": sum(g["action"] == "update" for g in groups),
            "groups_unchanged": sum(g["action"] == "unchanged" for g in groups),
            "groups_needs_review": sum(g["action"] == "needs_review" for g in groups),
            "groups_blocked": sum(g["action"] == "blocked" for g in groups),
            "groups_deferred": sum(
                g["customer_resolution_status"] in {
                    "needs_review", "blocked"
                } or g["action"] == "blocked"
                for g in groups
            ),
        }

    @classmethod
    def _store(cls, upload: FileStorage) -> tuple[Path, str]:
        if not upload or not upload.filename:
            raise OpportunityImportValidationError(
                "Seleccione un archivo para importar."
            )
        extension = Path(upload.filename).suffix.lower()
        if extension not in cls.ALLOWED_EXTENSIONS:
            raise OpportunityImportValidationError(
                "Formato no soportado. Use .xlsx, .xls o .csv."
            )
        cls.STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        temporary = cls.STORAGE_ROOT / f"pending-{secure_filename(upload.filename)}"
        upload.save(temporary)
        file_hash = cls._hash(temporary)
        stored = cls.STORAGE_ROOT / f"{file_hash}{extension}"
        if stored.exists():
            temporary.unlink()
        else:
            temporary.replace(stored)
        return stored, file_hash

    @staticmethod
    def _read(
        path: Path, profile: dict[str, Any] | None = None
    ) -> pd.DataFrame:
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path, dtype=object)
        sheet_name = (
            (profile or {}).get("grouping_configuration", {}).get("sheet_name")
        )
        try:
            return pd.read_excel(
                path, sheet_name=sheet_name or 0, dtype=object
            )
        except ValueError as error:
            raise OpportunityImportValidationError(
                f"El libro no contiene la hoja configurada: {sheet_name}."
            ) from error

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
