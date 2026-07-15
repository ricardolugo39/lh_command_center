from pathlib import Path
from uuid import uuid4
import shutil

from werkzeug.datastructures import FileStorage

from app.workspace.repositories.project_file_repository import (
    ProjectFileRepository,
)

UPLOAD_ROOT = Path("uploads/projects")


class ProjectFileService:

    ALLOWED_EXTENSIONS = {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".png",
        ".jpg",
        ".jpeg",
        ".txt",
        ".zip",
    }

    @staticmethod
    def upload_file(
        *,
        project_id: int,
        file: FileStorage,
        category: str,
        uploaded_by: str = "system",
    ):

        if file.filename == "":
            raise ValueError(
                "Seleccione un archivo."
            )

        extension = (
            Path(file.filename)
            .suffix
            .lower()
        )

        if extension not in (
            ProjectFileService.ALLOWED_EXTENSIONS
        ):
            raise ValueError(
                "Tipo de archivo no permitido."
            )

        project_folder = (
            UPLOAD_ROOT / str(project_id)
        )

        project_folder.mkdir(
            parents=True,
            exist_ok=True,
        )

        stored_name = (
            f"{uuid4().hex}{extension}"
        )

        destination = (
            project_folder / stored_name
        )

        file.save(destination)

        return ProjectFileRepository.create_file(
            project_id=project_id,
            category=category,
            original_name=file.filename,
            stored_name=stored_name,
            mime_type=file.mimetype,
            file_size=destination.stat().st_size,
            uploaded_by=uploaded_by,
        )

    @staticmethod
    def delete_file(
        file_id: int,
    ):

        record = (
            ProjectFileRepository.get_file(
                file_id
            )
        )

        if record is None:
            raise ValueError(
                "Archivo no encontrado."
            )

        path = (
            UPLOAD_ROOT
            / str(record["project_id"])
            / record["stored_name"]
        )

        if path.exists():
            path.unlink()

        ProjectFileRepository.delete_file(
            file_id
        )

    @staticmethod
    def get_file_path(
        file_id: int,
    ):

        record = (
            ProjectFileRepository.get_file(
                file_id
            )
        )

        if record is None:
            raise ValueError(
                "Archivo no encontrado."
            )

        return (
            record,
            UPLOAD_ROOT
            / str(record["project_id"])
            / record["stored_name"],
        )