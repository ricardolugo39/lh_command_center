import json
from typing import Any

from app.database.transaction import connection_scope


class AskRepository:
    JSON_FIELDS = {
        "context": "context_json", "mappings": "mappings_json",
        "assumptions": "assumptions_json", "plan": "plan_json",
        "blocking_reasons": "blocking_reasons_json",
        "evidence": "evidence_json", "ai_response": "ai_response_json",
    }

    @staticmethod
    def create_analysis(values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO ask_analyses (
                    root_analysis_id, parent_analysis_id, version, title,
                    objective, focus, status, customer_id, customer_site_id,
                    context_json, mappings_json, assumptions_json, plan_json,
                    blocking_reasons_json, created_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    values.get("root_analysis_id"),
                    values.get("parent_analysis_id"), values.get("version", 1),
                    values["title"], values["objective"], values.get("focus"),
                    values.get("status", "draft"), values.get("customer_id"),
                    values.get("customer_site_id"),
                    json.dumps(values.get("context", {}), ensure_ascii=False),
                    json.dumps(values.get("mappings", {}), ensure_ascii=False),
                    json.dumps(values.get("assumptions", {}), ensure_ascii=False),
                    json.dumps(values.get("plan", []), ensure_ascii=False),
                    json.dumps(
                        values.get("blocking_reasons", []), ensure_ascii=False
                    ),
                    values["created_by_user_id"],
                ),
            )
            analysis_id = int(cursor.lastrowid)
            if not values.get("root_analysis_id"):
                connection.execute(
                    "UPDATE ask_analyses SET root_analysis_id=? WHERE id=?",
                    (analysis_id, analysis_id),
                )
            return analysis_id

    @classmethod
    def get(cls, analysis_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                """SELECT a.*, u.display_name AS created_by_name,
                    c.name AS customer_name, c.erp_customer_id
                FROM ask_analyses a
                JOIN ws_users u ON u.id=a.created_by_user_id
                LEFT JOIN ws_customers c ON c.id=a.customer_id
                WHERE a.id=?""", (analysis_id,)
            ).fetchone()
        return cls._decode(dict(row)) if row else None

    @classmethod
    def list_visible(
        cls, user_id: int, can_view_all: bool, limit: int = 50
    ) -> list[dict[str, Any]]:
        where = "" if can_view_all else "WHERE a.created_by_user_id=?"
        params = (limit,) if can_view_all else (user_id, limit)
        with connection_scope() as connection:
            rows = connection.execute(
                f"""SELECT a.*, c.name AS customer_name,
                    u.display_name AS created_by_name
                FROM ask_analyses a
                JOIN ws_users u ON u.id=a.created_by_user_id
                LEFT JOIN ws_customers c ON c.id=a.customer_id
                {where} ORDER BY a.updated_at DESC, a.id DESC LIMIT ?""",
                params,
            ).fetchall()
        return [cls._decode(dict(row)) for row in rows]

    @classmethod
    def update(cls, analysis_id: int, values: dict[str, Any]) -> None:
        allowed = {
            "title", "objective", "focus", "status", "customer_id",
            "customer_site_id", "report_html", "error_message", "executed_at",
            "lifecycle_status",
        }
        assignments, params = [], []
        for key, value in values.items():
            if key in cls.JSON_FIELDS:
                assignments.append(f"{cls.JSON_FIELDS[key]}=?")
                params.append(json.dumps(value, ensure_ascii=False, default=str))
            elif key in allowed:
                assignments.append(f"{key}=?")
                params.append(value)
        if not assignments:
            return
        assignments.append("updated_at=CURRENT_TIMESTAMP")
        params.append(analysis_id)
        with connection_scope() as connection:
            connection.execute(
                f"UPDATE ask_analyses SET {','.join(assignments)} WHERE id=?",
                tuple(params),
            )

    @staticmethod
    def add_message(analysis_id: int, values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO ask_messages (
                    analysis_id, role, content, clarification_type,
                    related_entity_type, related_entity_id, resolved_action
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id, values["role"], values["content"],
                    values.get("clarification_type"),
                    values.get("related_entity_type"),
                    values.get("related_entity_id"),
                    values.get("resolved_action"),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def list_messages(analysis_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM ask_messages WHERE analysis_id=?
                ORDER BY created_at,id""", (analysis_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def add_file(analysis_id: int, values: dict[str, Any]) -> int:
        with connection_scope() as connection:
            cursor = connection.execute(
                """INSERT INTO ask_files (
                    analysis_id, original_filename, stored_filename,
                    stored_path, file_extension, mime_type, file_size_bytes,
                    file_hash, processing_status, inspection_json, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id, values["original_filename"],
                    values["stored_filename"], values["stored_path"],
                    values["file_extension"], values.get("mime_type"),
                    values["file_size_bytes"], values["file_hash"],
                    values["processing_status"],
                    json.dumps(values.get("inspection", {}), ensure_ascii=False,
                               default=str),
                    values.get("error_message"),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def list_files(analysis_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM ask_files WHERE analysis_id=?
                ORDER BY uploaded_at,id""", (analysis_id,)
            ).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value["inspection"] = json.loads(value["inspection_json"] or "{}")
            result.append(value)
        return result

    @staticmethod
    def get_file(file_id: int) -> dict[str, Any] | None:
        with connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM ask_files WHERE id=?", (file_id,)
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        value["inspection"] = json.loads(value["inspection_json"] or "{}")
        return value

    @staticmethod
    def delete_file(file_id: int) -> None:
        with connection_scope() as connection:
            connection.execute("DELETE FROM ask_files WHERE id=?", (file_id,))

    @staticmethod
    def next_version(root_analysis_id: int) -> int:
        with connection_scope() as connection:
            return int(connection.execute(
                """SELECT COALESCE(MAX(version),0)+1 FROM ask_analyses
                WHERE root_analysis_id=?""", (root_analysis_id,)
            ).fetchone()[0])

    @staticmethod
    def replace_artifacts(
        analysis_id: int, artifacts: list[dict[str, Any]]
    ) -> None:
        with connection_scope() as connection:
            connection.execute(
                "DELETE FROM ask_artifacts WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.executemany(
                """INSERT INTO ask_artifacts(
                    analysis_id,artifact_key,artifact_type,title,position,
                    artifact_json
                ) VALUES(?,?,?,?,?,?)""",
                [
                    (
                        analysis_id, artifact["key"], artifact["type"],
                        artifact["title"], position,
                        json.dumps(
                            artifact, ensure_ascii=False, default=str
                        ),
                    )
                    for position, artifact in enumerate(artifacts)
                ],
            )

    @staticmethod
    def list_artifacts(analysis_id: int) -> list[dict[str, Any]]:
        with connection_scope() as connection:
            rows = connection.execute(
                """SELECT * FROM ask_artifacts WHERE analysis_id=?
                ORDER BY position,id""", (analysis_id,)
            ).fetchall()
        artifacts = []
        for row in rows:
            value = json.loads(row["artifact_json"] or "{}")
            value.setdefault("id", row["id"])
            value.setdefault("key", row["artifact_key"])
            value.setdefault("type", row["artifact_type"])
            value.setdefault("title", row["title"])
            artifacts.append(value)
        return artifacts

    @classmethod
    def _decode(cls, value: dict[str, Any]) -> dict[str, Any]:
        for target, source in cls.JSON_FIELDS.items():
            try:
                value[target] = json.loads(value.get(source) or (
                    "[]" if target in {"plan", "blocking_reasons"} else "{}"
                ))
            except json.JSONDecodeError:
                value[target] = [] if target in {
                    "plan", "blocking_reasons"
                } else {}
        return value
