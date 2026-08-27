from typing import Any

from app.workspace.repositories.project_file_repository import ProjectFileRepository
from app.workspace.timeline.entry import (
    TimelineCategory,
    TimelineEntry,
    TimelineEventType,
)
from app.workspace.timeline.providers.base import TimelineProvider


class FileTimelineProvider(TimelineProvider):
    event_type = TimelineEventType.FILE

    def get_events(
        self,
        project_id: int,
        records: list[dict[str, Any]] | None = None,
    ) -> list[TimelineEntry]:
        rows = (
            records
            if records is not None
            else ProjectFileRepository.list_project_files(project_id)
        )
        return [self._entry(row) for row in rows]

    @classmethod
    def _entry(cls, file: dict[str, Any]) -> TimelineEntry:
        return TimelineEntry(
            id=f"file-{file['id']}",
            event_type=cls.event_type,
            icon="paperclip",
            color="neutral",
            title=f"Archivo {file['original_name']} cargado",
            description=f"Categoría: {file.get('category') or 'otro'}",
            source="Archivo",
            reference_id=file["id"],
            date=file.get("created_at"),
            user=file.get("uploaded_by") or "Sistema",
            endpoint="workspace.download_project_file",
            endpoint_values={"file_id": file["id"]},
            category=TimelineCategory.SYSTEM,
        )
