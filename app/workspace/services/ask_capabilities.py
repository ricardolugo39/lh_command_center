from typing import Any, Protocol

from app.workspace.repositories.ask_context_repository import (
    AskContextRepository,
)
from app.workspace.services.ask_file_service import AskFileService


class AskCapability(Protocol):
    name: str

    def execute(
        self, analysis: dict[str, Any], files: list[dict[str, Any]]
    ) -> dict[str, Any]: ...


class UploadedEvidenceCapability:
    name = "uploaded_evidence"

    def execute(self, analysis, files):
        facts, metrics, findings, trace, rows = [], [], [], [], []
        evidence = [
            AskFileService.structured_evidence(file) for file in files
        ]
        for item in evidence:
            trace.append({
                "step": f"Archivo inspeccionado: {item['filename']}",
                "status": item["processing_status"],
                "source_file_id": item["file_id"],
            })
            if item["processing_status"] != "processed":
                findings.append({
                    "statement": (
                        f"No fue posible validar el contenido de "
                        f"{item['filename']}."
                    ),
                    "confidence": "Alta",
                    "evidence_file_ids": [item["file_id"]],
                })
                continue
            facts.append({
                "statement": item["evidence"].get("summary")
                or f"{item['filename']} fue procesado.",
                "evidence_file_ids": [item["file_id"]],
            })
            if item["file_type"] != "spreadsheet":
                continue
            file_record = next(
                file for file in files if file["id"] == item["file_id"]
            )
            inspection = file_record["inspection"]
            for table in inspection.get("tables", []):
                for column in table.get("columns", []):
                    metrics.append({
                        "name": (
                            f"{item['filename']} · {table['name']} · "
                            f"{column['name']} · valores informados"
                        ),
                        "value": column["non_null_count"],
                        "source_file_id": item["file_id"],
                    })
                rows.extend(
                    {
                        "source_file_id": item["file_id"],
                        "source_file": item["filename"],
                        "source_table": table["name"],
                        **row,
                    }
                    for row in table.get("sample_rows", [])
                )
                findings.extend(self._table_findings(item, table))
        return {
            "facts": facts, "metrics": metrics, "findings": findings,
            "trace": trace, "working_dataset": rows[:500],
            "supporting_evidence": evidence,
        }

    @staticmethod
    def _table_findings(file_evidence, table):
        findings = []
        empty_columns = [
            column["name"] for column in table.get("columns", [])
            if not column["non_null_count"]
        ]
        if empty_columns:
            findings.append({
                "statement": (
                    f"{table['name']} contiene {len(empty_columns)} columna(s) "
                    "sin valores."
                ),
                "confidence": "Alta",
                "evidence_file_ids": [file_evidence["file_id"]],
            })
        if not table["row_count"]:
            findings.append({
                "statement": f"{table['name']} no contiene filas de datos.",
                "confidence": "Alta",
                "evidence_file_ids": [file_evidence["file_id"]],
            })
        return findings


class CustomerContextCapability:
    name = "customer_context"

    def execute(self, analysis, files):
        customer = analysis.get("context", {}).get("customer")
        if not customer:
            return {}
        records = AskContextRepository.customer_commercial_records(
            customer["id"]
        )
        facts = [{
            "statement": f"Cliente resuelto: {customer['name']}.",
            "entity_type": "customer",
            "entity_id": customer["id"],
        }]
        metrics = [
            {
                "name": f"Registros disponibles · {name}",
                "value": len(values),
                "source": "Commercial Command Center",
            }
            for name, values in records.items()
        ]
        return {
            "facts": facts,
            "metrics": metrics,
            "findings": [],
            "trace": [{
                "step": "Contexto comercial del cliente consultado",
                "status": "completed",
            }],
            "supporting_evidence": [{
                "source": "Commercial Command Center",
                "record_counts": {
                    name: len(values) for name, values in records.items()
                },
            }],
            "working_dataset": [],
        }


class AskCapabilityRegistry:
    _capabilities = {
        capability.name: capability
        for capability in (
            UploadedEvidenceCapability(),
            CustomerContextCapability(),
        )
    }

    @classmethod
    def execute(
        cls, names: list[str], analysis: dict[str, Any],
        files: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            cls._capabilities[name].execute(analysis, files)
            for name in names if name in cls._capabilities
        ]
