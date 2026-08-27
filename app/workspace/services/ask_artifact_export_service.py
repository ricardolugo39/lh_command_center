import io
from typing import Any

import pandas as pd

from app.workspace.repositories.ask_repository import AskRepository


class AskArtifactExportService:
    """Exports any table artifact without knowing its business domain."""

    @staticmethod
    def export(
        analysis_id: int, artifact_key: str, output_format: str
    ) -> tuple[io.BytesIO, str, str]:
        artifact = next((
            item for item in AskRepository.list_artifacts(analysis_id)
            if item["key"] == artifact_key
        ), None)
        if not artifact:
            raise ValueError("El entregable no existe.")
        tables = [
            block for block in artifact.get("blocks", [])
            if block.get("type") == "table"
        ]
        if not tables:
            raise ValueError("El entregable no contiene datos exportables.")
        rows: list[dict[str, Any]] = []
        for table in tables:
            for row in table.get("rows", []):
                rows.append({
                    "_tabla": table.get("title") or "Datos",
                    **row,
                })
        frame = pd.DataFrame(rows)
        stream = io.BytesIO()
        safe_key = "".join(
            character if character.isalnum() or character in "-_"
            else "-"
            for character in artifact_key
        ).strip("-") or "entregable"
        if output_format == "csv":
            stream.write(frame.to_csv(index=False).encode("utf-8-sig"))
            mimetype = "text/csv"
            filename = f"{safe_key}.csv"
        elif output_format == "xlsx":
            frame.to_excel(stream, index=False, sheet_name="Datos")
            mimetype = (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
            filename = f"{safe_key}.xlsx"
        else:
            raise ValueError("Formato de exportación no soportado.")
        stream.seek(0)
        return stream, mimetype, filename
