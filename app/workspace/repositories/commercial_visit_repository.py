import json
from typing import Any

from app.database.transaction import connection_scope


class CommercialVisitRepository:
    FIELDS = (
        "source_row_hash","source_created_at","visit_date","advisor_name",
        "customer_id","customer_erp_id","source_customer_name","customer_match_status",
        "visited_contact_name","visited_contact_role","visit_type","source_visit_type",
        "visit_reason","executive_summary","detected_need","detected_risk",
        "competitor","key_comments","requires_action","required_action",
        "follow_up_owner_name","commitment_date","generate_opportunity_requested",
        "visit_status","source_visit_status","attachment_reference","project_id",
        "possible_duplicate","quality_warnings","source_payload_json",
    )

    @staticmethod
    def get(visit_id: int):
        with connection_scope() as conn:
            row=conn.execute("SELECT * FROM ws_commercial_visits WHERE id=?",(visit_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_by_source(source_system: str, source_visit_id: str):
        with connection_scope() as conn:
            row=conn.execute("SELECT * FROM ws_commercial_visits WHERE source_system=? AND source_visit_id=?",(source_system,source_visit_id)).fetchone()
            return dict(row) if row else None

    @classmethod
    def insert(cls, source_system: str, values: dict[str, Any]) -> int:
        columns=",".join(cls.FIELDS); placeholders=",".join("?" for _ in cls.FIELDS)
        with connection_scope() as conn:
            cursor=conn.execute(f"""INSERT INTO ws_commercial_visits(
                source_system,source_visit_id,{columns}) VALUES (?,?,{placeholders})""",
                (source_system,values["source_visit_id"],*[cls._value(field,values) for field in cls.FIELDS]))
            return int(cursor.lastrowid)

    @classmethod
    def update(cls, visit_id: int, values: dict[str,Any]) -> None:
        assignments=",".join(f"{field}=?" for field in cls.FIELDS)
        with connection_scope() as conn:
            conn.execute(f"UPDATE ws_commercial_visits SET {assignments},last_synced_at=CURRENT_TIMESTAMP WHERE id=?",
                         (*[cls._value(field,values) for field in cls.FIELDS],visit_id))

    @staticmethod
    def _value(field, values):
        value=values.get(field)
        if field=="quality_warnings": return json.dumps(value or [],ensure_ascii=False)
        return value

    @staticmethod
    def find_possible_duplicate(values: dict, exclude_source_id: str):
        with connection_scope() as conn:
            row=conn.execute("""SELECT id FROM ws_commercial_visits
                WHERE source_visit_id<>? AND COALESCE(customer_erp_id,'')=COALESCE(?, '')
                  AND COALESCE(visit_date,'')=COALESCE(?, '')
                  AND LOWER(COALESCE(advisor_name,''))=LOWER(COALESCE(?,''))
                  AND LOWER(COALESCE(visit_reason,''))=LOWER(COALESCE(?,''))
                  AND LOWER(COALESCE(visited_contact_name,''))=LOWER(COALESCE(?,''))
                  AND COALESCE(attachment_reference,'')=COALESCE(?, '') LIMIT 1""",
                (exclude_source_id,values.get("customer_erp_id"),values.get("visit_date"),
                 values.get("advisor_name"),values.get("visit_reason"),
                 values.get("visited_contact_name"),values.get("attachment_reference"))).fetchone()
            return bool(row)

    @staticmethod
    def list_customer(customer_id: int):
        with connection_scope() as conn:
            return [dict(row) for row in conn.execute("""SELECT * FROM ws_commercial_visits
                WHERE customer_id=? AND is_active=1 ORDER BY visit_date DESC,id DESC""",
                (customer_id,)).fetchall()]

    @staticmethod
    def list_advisor(advisor_name: str):
        with connection_scope() as conn:
            rows = conn.execute(
                """SELECT v.*,c.name AS customer_name
                FROM ws_commercial_visits v
                LEFT JOIN ws_customers c ON c.id=v.customer_id
                WHERE v.is_active=1 AND LOWER(TRIM(v.advisor_name))=LOWER(TRIM(?))
                ORDER BY v.visit_date DESC,v.id DESC""",
                (advisor_name,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_project(project_id: int) -> list[dict[str, Any]]:
        with connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM ws_commercial_visits
                WHERE project_id = ? AND is_active = 1
                ORDER BY COALESCE(visit_date, imported_at) DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def list_quality_issues():
        with connection_scope() as conn:
            return [dict(row) for row in conn.execute("""SELECT * FROM ws_commercial_visits
                WHERE customer_match_status<>'matched' OR possible_duplicate=1
                   OR quality_warnings<>'[]' OR (attachment_reference IS NOT NULL AND attachment_reference<>'')
                ORDER BY last_synced_at DESC""").fetchall()]

    @staticmethod
    def get_manual_match(source_key: str):
        with connection_scope() as conn:
            row=conn.execute("SELECT customer_id FROM ws_visit_customer_matches WHERE source_customer_key=?",(source_key,)).fetchone()
            return row["customer_id"] if row else None

    @staticmethod
    def upsert_followup(visit_id: int, source_visit_id: str, values: dict):
        key=f"appsheet_visit:{source_visit_id}:follow_up"
        source_status = str(values.get("visit_status") or "").strip().casefold()
        lifecycle_status = (
            "completed" if source_status in {"cerrado", "closed", "completado", "completed"}
            else "pending"
        )
        with connection_scope() as conn:
            similar = conn.execute(
                """SELECT vf.id FROM ws_visit_followups vf
                INNER JOIN ws_commercial_visits previous ON previous.id=vf.visit_id
                INNER JOIN ws_commercial_visits current ON current.id=?
                WHERE vf.status='pending'
                  AND previous.customer_id=current.customer_id
                  AND LOWER(TRIM(COALESCE(vf.description,'')))=
                      LOWER(TRIM(COALESCE(?,'')))
                  AND vf.external_key<>?
                ORDER BY vf.updated_at DESC LIMIT 1""",
                (visit_id, values.get("required_action"), key),
            ).fetchone()
            if similar:
                conn.execute(
                    """UPDATE ws_visit_followups SET visit_id=?,external_key=?,
                    description=?,owner_name=?,due_date=?,status=?,
                    completed_at=CASE WHEN ?='completed' THEN CURRENT_TIMESTAMP
                        ELSE completed_at END,updated_at=CURRENT_TIMESTAMP
                    WHERE id=?""",
                    (visit_id, key, values.get("required_action"),
                     values.get("follow_up_owner_name"), values.get("commitment_date"),
                     lifecycle_status, lifecycle_status,
                     similar["id"]),
                )
                return
            conn.execute("""INSERT INTO ws_visit_followups(visit_id,external_key,description,owner_name,due_date,status)
                VALUES (?,?,?,?,?,?) ON CONFLICT(external_key) DO UPDATE SET
                description=excluded.description,owner_name=excluded.owner_name,
                due_date=CASE WHEN ws_visit_followups.status='completed'
                    THEN ws_visit_followups.due_date ELSE excluded.due_date END,
                status=CASE WHEN ws_visit_followups.status='completed'
                    THEN 'completed' ELSE excluded.status END,
                updated_at=CURRENT_TIMESTAMP""",
                (visit_id,key,values.get("required_action"),values.get("follow_up_owner_name"),
                 values.get("commitment_date"),lifecycle_status))

    @staticmethod
    def complete_followup(followup_id: int) -> None:
        with connection_scope() as conn:
            cursor = conn.execute(
                """UPDATE ws_visit_followups
                SET status='completed',completed_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (followup_id,),
            )
            if cursor.rowcount == 0:
                raise ValueError("El compromiso de visita no existe.")

    @staticmethod
    def close_source_followup(source_visit_id: str) -> None:
        with connection_scope() as conn:
            conn.execute(
                """UPDATE ws_visit_followups SET status='completed',
                    completed_at=COALESCE(completed_at,CURRENT_TIMESTAMP),
                    updated_at=CURRENT_TIMESTAMP
                WHERE external_key=? AND status='pending'""",
                (f"appsheet_visit:{source_visit_id}:follow_up",),
            )

    @staticmethod
    def reschedule_followup(followup_id: int, due_date: str, reason: str) -> None:
        if not due_date.strip() or not reason.strip():
            raise ValueError("La fecha y el motivo de reprogramación son obligatorios.")
        with connection_scope() as conn:
            cursor = conn.execute(
                """UPDATE ws_visit_followups SET due_date=?,reschedule_reason=?,
                    reschedule_count=COALESCE(reschedule_count,0)+1,
                    updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'""",
                (due_date.strip(), reason.strip(), followup_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("El compromiso no existe o ya está cerrado.")

    @staticmethod
    def create_sync_run(source_system: str) -> int:
        with connection_scope() as conn:
            return int(conn.execute("INSERT INTO ws_visit_sync_runs(source_system,status) VALUES (?,'running')",(source_system,)).lastrowid)

    @staticmethod
    def finish_sync_run(run_id: int, summary: dict, status="completed"):
        with connection_scope() as conn:
            conn.execute("""UPDATE ws_visit_sync_runs SET completed_at=CURRENT_TIMESTAMP,status=?,
                rows_read=?,inserted_count=?,updated_count=?,unchanged_count=?,unmatched_count=?,
                possible_duplicate_count=?,error_count=?,error_summary=? WHERE id=?""",
                (status,summary["rows_read"],summary["inserted"],summary["updated"],summary["unchanged"],
                 summary["unmatched"],summary["possible_duplicates"],summary["errors"],
                 json.dumps(summary.get("error_details",[]),ensure_ascii=False),run_id))

    @staticmethod
    def latest_sync_run():
        with connection_scope() as conn:
            row=conn.execute("SELECT * FROM ws_visit_sync_runs ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    @staticmethod
    def integration_metrics() -> dict:
        with connection_scope() as conn:
            row = conn.execute(
                """SELECT
                    COUNT(*) AS imported_visits,
                    SUM(CASE WHEN customer_match_status <> 'matched'
                        THEN 1 ELSE 0 END) AS unmatched,
                    SUM(CASE WHEN possible_duplicate = 1
                        THEN 1 ELSE 0 END) AS possible_duplicates,
                    SUM(CASE WHEN quality_warnings <> '[]'
                        THEN 1 ELSE 0 END) AS warning_records
                FROM ws_commercial_visits
                WHERE source_system = ? AND is_active = 1""",
                ("appsheet_google_sheets",),
            ).fetchone()
        return dict(row)

    @staticmethod
    def customer_quality(customer_id: int) -> dict:
        with connection_scope() as conn:
            row = conn.execute(
                """SELECT COUNT(*) total,
                    SUM(CASE WHEN possible_duplicate=1 OR quality_warnings<>'[]' THEN 1 ELSE 0 END) warnings,
                    MAX(last_synced_at) last_record_sync
                FROM ws_commercial_visits WHERE customer_id=? AND is_active=1""",
                (customer_id,),
            ).fetchone()
        result = dict(row)
        latest = CommercialVisitRepository.latest_sync_run()
        result["latest_sync"] = latest.get("completed_at") if latest else None
        return result

    @staticmethod
    def list_source_project_links(source_system: str) -> dict[str, int]:
        with connection_scope() as conn:
            rows=conn.execute("""SELECT source_visit_id,project_id
                FROM ws_commercial_visits
                WHERE source_system=? AND project_id IS NOT NULL""",
                (source_system,)).fetchall()
            return {row["source_visit_id"]:row["project_id"] for row in rows}

    @staticmethod
    def delete_source(source_system: str) -> int:
        with connection_scope() as conn:
            ids=[row["id"] for row in conn.execute(
                "SELECT id FROM ws_commercial_visits WHERE source_system=?",
                (source_system,)).fetchall()]
            for visit_id in ids:
                conn.execute("DELETE FROM ws_activities WHERE details LIKE ?",
                             (f"%[visita:{visit_id}]%",))
            cursor=conn.execute(
                "DELETE FROM ws_commercial_visits WHERE source_system=?",
                (source_system,))
            return cursor.rowcount

    @staticmethod
    def has_project_event(project_id: int, visit_id: int) -> bool:
        marker=f"[visita:{visit_id}]"
        with connection_scope() as conn:
            return bool(conn.execute("SELECT 1 FROM ws_activities WHERE project_id=? AND details LIKE ? LIMIT 1",(project_id,f"%{marker}%")).fetchone())

    @staticmethod
    def link_project(visit_id: int, project_id: int):
        with connection_scope() as conn:
            conn.execute("UPDATE ws_commercial_visits SET project_id=? WHERE id=?",(project_id,visit_id))
