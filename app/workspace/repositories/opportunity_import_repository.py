import json
from typing import Any

from app.database.transaction import connection_scope


class OpportunityImportRepository:
    """Persistence for versioned, source-neutral Opportunity import profiles."""

    @staticmethod
    def create_profile(
        name: str, *, created_by: str, active: bool = False
    ) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO opportunity_import_profiles(
                    profile_name, is_active, created_by, updated_by
                ) VALUES (?, ?, ?, ?)""",
                (name.strip(), int(active), created_by, created_by),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def add_version(
        profile_id: int,
        *,
        mapping: dict[str, Any],
        transformations: dict[str, Any] | None = None,
        grouping: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        ownership: dict[str, Any] | None = None,
        created_by: str,
    ) -> int:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT COALESCE(MAX(version), 0) + 1
                FROM opportunity_import_profile_versions
                WHERE profile_id=?""",
                (profile_id,),
            ).fetchone()
            version = int(row[0])
            cursor = connection.execute(
                """INSERT INTO opportunity_import_profile_versions(
                    profile_id, version, column_mapping_json,
                    transformation_rules_json, grouping_configuration_json,
                    validation_configuration_json,
                    ownership_configuration_json, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile_id, version,
                    json.dumps(mapping, ensure_ascii=False),
                    json.dumps(transformations or {}, ensure_ascii=False),
                    json.dumps(grouping or {}, ensure_ascii=False),
                    json.dumps(validation or {}, ensure_ascii=False),
                    json.dumps(ownership or {}, ensure_ascii=False),
                    created_by,
                ),
            )
            connection.execute(
                """UPDATE opportunity_import_profiles
                SET current_version=?, updated_by=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (version, created_by, profile_id),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def activate(profile_id: int, *, updated_by: str) -> None:
        with connection_scope() as connection:
            connection.execute(
                "UPDATE opportunity_import_profiles SET is_active=0 "
                "WHERE import_origin='crm'"
            )
            connection.execute(
                """UPDATE opportunity_import_profiles
                SET is_active=1, updated_by=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (updated_by, profile_id),
            )

    @staticmethod
    def active_version() -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT v.*, p.profile_name
                FROM opportunity_import_profiles p
                JOIN opportunity_import_profile_versions v
                  ON v.profile_id=p.id AND v.version=p.current_version
                WHERE p.import_origin='crm' AND p.is_active=1
                LIMIT 1"""
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        for column in (
            "column_mapping_json", "transformation_rules_json",
            "grouping_configuration_json", "validation_configuration_json",
            "ownership_configuration_json",
        ):
            result[column.removesuffix("_json")] = json.loads(
                result[column] or "{}"
            )
        return result

    @staticmethod
    def profile_version(version_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT v.*, p.profile_name
                FROM opportunity_import_profile_versions v
                JOIN opportunity_import_profiles p ON p.id=v.profile_id
                WHERE v.id=?""",
                (version_id,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        for column in (
            "column_mapping_json", "transformation_rules_json",
            "grouping_configuration_json", "validation_configuration_json",
            "ownership_configuration_json",
        ):
            result[column.removesuffix("_json")] = json.loads(
                result[column] or "{}"
            )
        return result

    @staticmethod
    def upsert_resolution(
        execution_id: int, external_id: str, *,
        source_customer_key: str | None, status: str,
        customer_id: int | None, resolved_by: str | None = None,
    ) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO opportunity_import_customer_resolutions(
                    import_execution_id, external_opportunity_id,
                    source_customer_key, customer_id, resolution_status,
                    resolved_by
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(import_execution_id, external_opportunity_id)
                DO UPDATE SET customer_id=excluded.customer_id,
                    resolution_status=excluded.resolution_status,
                    resolved_by=excluded.resolved_by,
                    updated_at=CURRENT_TIMESTAMP""",
                (
                    execution_id, external_id, source_customer_key,
                    customer_id, status, resolved_by,
                ),
            )

    @staticmethod
    def resolutions(execution_id: int) -> dict[str, dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM opportunity_import_customer_resolutions
                WHERE import_execution_id=?""",
                (execution_id,),
            ).fetchall()
        return {str(row["external_opportunity_id"]): dict(row) for row in rows}

    @staticmethod
    def customer_alias(normalized_identity: str) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT * FROM opportunity_import_customer_aliases
                WHERE normalized_source_identity=?""",
                (normalized_identity,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def save_customer_alias(
        normalized_identity: str, source_name: str, customer_id: int,
        *, confirmed_by: str,
    ) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO opportunity_import_customer_aliases(
                    normalized_source_identity, source_display_name,
                    customer_id, match_reason, confirmed_by
                ) VALUES (?, ?, ?, 'user_confirmed', ?)
                ON CONFLICT(normalized_source_identity) DO UPDATE SET
                    source_display_name=excluded.source_display_name,
                    customer_id=excluded.customer_id,
                    confirmed_by=excluded.confirmed_by,
                    updated_at=CURRENT_TIMESTAMP""",
                (
                    normalized_identity, source_name, customer_id,
                    confirmed_by,
                ),
            )

    @staticmethod
    def upsert_seller_resolution(
        execution_id: int, external_id: str, *, source_seller: str | None,
        status: str, resolved_sales_rep: str | None,
        match_reason: str | None = None, resolved_by: str | None = None,
    ) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO opportunity_import_seller_resolutions(
                    import_execution_id, external_opportunity_id,
                    source_seller, resolved_sales_rep, resolution_status,
                    match_reason, resolved_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(import_execution_id, external_opportunity_id)
                DO UPDATE SET
                    resolved_sales_rep=excluded.resolved_sales_rep,
                    resolution_status=excluded.resolution_status,
                    match_reason=excluded.match_reason,
                    resolved_by=excluded.resolved_by,
                    updated_at=CURRENT_TIMESTAMP""",
                (
                    execution_id, external_id, source_seller,
                    resolved_sales_rep, status, match_reason, resolved_by,
                ),
            )

    @staticmethod
    def seller_resolutions(execution_id: int) -> dict[str, dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM opportunity_import_seller_resolutions
                WHERE import_execution_id=?""",
                (execution_id,),
            ).fetchall()
        return {str(row["external_opportunity_id"]): dict(row) for row in rows}

    @staticmethod
    def seller_alias(normalized_seller: str) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT * FROM opportunity_import_seller_aliases
                WHERE normalized_source_seller=?""",
                (normalized_seller,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def save_seller_alias(
        normalized_seller: str, source_seller: str, resolved_sales_rep: str,
        *, confirmed_by: str,
    ) -> None:
        with connection_scope() as connection:
            connection.execute(
                """INSERT INTO opportunity_import_seller_aliases(
                    normalized_source_seller, source_display_name,
                    resolved_sales_rep, match_reason, confirmed_by
                ) VALUES (?, ?, ?, 'user_confirmed', ?)
                ON CONFLICT(normalized_source_seller) DO UPDATE SET
                    source_display_name=excluded.source_display_name,
                    resolved_sales_rep=excluded.resolved_sales_rep,
                    confirmed_by=excluded.confirmed_by,
                    updated_at=CURRENT_TIMESTAMP""",
                (
                    normalized_seller, source_seller, resolved_sales_rep,
                    confirmed_by,
                ),
            )

    @staticmethod
    def seller_candidates() -> list[str]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT display_name AS value FROM ws_users WHERE is_active=1
                UNION
                SELECT sales_rep FROM ws_projects
                WHERE TRIM(COALESCE(sales_rep,''))<>''
                UNION
                SELECT seller FROM dim_customer
                WHERE TRIM(COALESCE(seller,''))<>''
                ORDER BY value COLLATE NOCASE"""
            ).fetchall()
        return [str(row[0]) for row in rows]

    @staticmethod
    def upsert_pending(
        group: dict[str, Any], *, execution_id: int,
        profile_version_id: int, actor: str,
    ) -> int:
        external_id = str(group["external_opportunity_id"])
        normalized = str(group.get("normalized_customer_identity") or "")
        with connection_scope() as connection:
            existing = connection.execute(
                """SELECT * FROM crm_opportunity_pending
                WHERE external_opportunity_id=?""",
                (external_id,),
            ).fetchone()
            previous_status = existing["resolution_status"] if existing else None
            preserved_customer = (
                int(existing["customer_id"])
                if existing and existing["customer_id"] is not None
                and existing["resolution_status"] == "ready"
                else None
            )
            new_status = "ready" if preserved_customer else (
                "blocked" if group["action"] == "blocked"
                else "needs_review"
            )
            if existing:
                connection.execute(
                    """UPDATE crm_opportunity_pending SET
                        origin_reference=?,source_company_name=?,
                        normalized_customer_identity=?,
                        customer_id=COALESCE(?,customer_id),
                        resolution_status=?,match_reason=?,
                        group_snapshot_json=?,latest_import_execution_id=?,
                        mapping_profile_version_id=?,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=?""",
                    (
                        group.get("origin_reference"),
                        group.get("customer_identity"),
                        normalized, preserved_customer, new_status,
                        group.get("customer_match_reason"),
                        json.dumps(group, ensure_ascii=False, default=str),
                        execution_id, profile_version_id, existing["id"],
                    ),
                )
                pending_id = int(existing["id"])
                event_type = "source_refreshed"
            else:
                cursor = connection.execute(
                    """INSERT INTO crm_opportunity_pending(
                        external_opportunity_id,origin_reference,
                        source_company_name,normalized_customer_identity,
                        customer_id,resolution_status,match_reason,
                        group_snapshot_json,original_import_execution_id,
                        latest_import_execution_id,mapping_profile_version_id
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        external_id, group.get("origin_reference"),
                        group.get("customer_identity"), normalized,
                        preserved_customer, new_status,
                        group.get("customer_match_reason"),
                        json.dumps(group, ensure_ascii=False, default=str),
                        execution_id, execution_id, profile_version_id,
                    ),
                )
                pending_id = int(cursor.lastrowid)
                event_type = "deferred"
            OpportunityImportRepository._record_pending_history(
                connection, pending_id, event_type=event_type,
                from_status=previous_status, to_status=new_status,
                execution_id=execution_id, actor=actor,
                details={"match_reason": group.get("customer_match_reason")},
            )
            return pending_id

    @staticmethod
    def list_pending(
        *, statuses: tuple[str, ...] = ("needs_review", "blocked", "ready")
    ) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in statuses)
        with connection_scope() as connection:
            rows = connection.execute(
                f"""SELECT p.*,c.name AS resolved_customer_name,
                    e.original_filename,e.stored_file_path,e.file_hash
                FROM crm_opportunity_pending p
                LEFT JOIN ws_customers c ON c.id=p.customer_id
                JOIN erp_import_executions e
                  ON e.id=p.latest_import_execution_id
                WHERE p.resolution_status IN ({placeholders})
                ORDER BY p.updated_at DESC,p.id DESC""",
                statuses,
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["group"] = json.loads(item["group_snapshot_json"])
            result.append(item)
        return result

    @staticmethod
    def get_pending(pending_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT p.*,e.original_filename,e.stored_file_path,e.file_hash
                FROM crm_opportunity_pending p
                JOIN erp_import_executions e
                  ON e.id=p.latest_import_execution_id
                WHERE p.id=?""",
                (pending_id,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["group"] = json.loads(result["group_snapshot_json"])
        return result

    @staticmethod
    def resolve_pending(
        pending_ids: list[int], *, customer_id: int,
        actor: str, alias_created: bool,
    ) -> int:
        if not pending_ids:
            return 0
        with connection_scope() as connection:
            updated = 0
            for pending_id in pending_ids:
                row = connection.execute(
                    "SELECT * FROM crm_opportunity_pending WHERE id=?",
                    (pending_id,),
                ).fetchone()
                if not row or row["resolution_status"] == "imported":
                    continue
                connection.execute(
                    """UPDATE crm_opportunity_pending SET
                        customer_id=?,resolution_status='ready',
                        resolved_by=?,resolved_at=CURRENT_TIMESTAMP,
                        alias_created=?,updated_at=CURRENT_TIMESTAMP
                    WHERE id=?""",
                    (
                        customer_id, actor, int(alias_created), pending_id,
                    ),
                )
                OpportunityImportRepository._record_pending_history(
                    connection, pending_id, event_type="customer_resolved",
                    from_status=row["resolution_status"], to_status="ready",
                    execution_id=row["latest_import_execution_id"],
                    actor=actor,
                    details={
                        "customer_id": customer_id,
                        "alias_created": alias_created,
                    },
                )
                updated += 1
            return updated

    @staticmethod
    def pending_ids_for_identity(normalized_identity: str) -> list[int]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT id FROM crm_opportunity_pending
                WHERE normalized_customer_identity=?
                  AND resolution_status IN ('needs_review','blocked','ready')""",
                (normalized_identity,),
            ).fetchall()
        return [int(row[0]) for row in rows]

    @staticmethod
    def mark_pending_imported(
        pending_id: int, *, opportunity_id: int,
        import_execution_id: int, actor: str,
    ) -> None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT resolution_status FROM crm_opportunity_pending WHERE id=?",
                (pending_id,),
            ).fetchone()
            if not row:
                return
            connection.execute(
                """UPDATE crm_opportunity_pending SET
                    resolution_status='imported',
                    imported_opportunity_id=?,
                    imported_import_execution_id=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (opportunity_id, import_execution_id, pending_id),
            )
            OpportunityImportRepository._record_pending_history(
                connection, pending_id, event_type="opportunity_imported",
                from_status=row["resolution_status"], to_status="imported",
                execution_id=import_execution_id, actor=actor,
                details={"opportunity_id": opportunity_id},
            )

    @staticmethod
    def pending_history(pending_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM crm_opportunity_pending_history
                WHERE pending_id=? ORDER BY created_at,id""",
                (pending_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _record_pending_history(
        connection, pending_id: int, *, event_type: str,
        from_status: str | None, to_status: str,
        execution_id: int | None, actor: str, details: dict[str, Any],
    ) -> None:
        connection.execute(
            """INSERT INTO crm_opportunity_pending_history(
                pending_id,event_type,from_status,to_status,
                import_execution_id,actor,details_json
            ) VALUES (?,?,?,?,?,?,?)""",
            (
                pending_id, event_type, from_status, to_status,
                execution_id, actor,
                json.dumps(details, ensure_ascii=False),
            ),
        )
