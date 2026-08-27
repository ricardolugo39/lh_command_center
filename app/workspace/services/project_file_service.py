from pathlib import Path
from uuid import uuid4

from werkzeug.datastructures import FileStorage

from app.workspace.repositories.project_file_repository import (
    ProjectFileRepository,
)
from app.workspace.services.project_access_policy import (
    ProjectAccessPolicy,
)
from app.database.transaction import transaction
from app.storage import upload_path

UPLOAD_ROOT = upload_path("projects")


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

        try:
            with transaction(write=True):
                ProjectAccessPolicy.require_writable(project_id)
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
        except Exception:
            if destination.exists():
                destination.unlink()
            raise

    @staticmethod
    def delete_file(
        file_id: int,
    ):

        path = None
        staged_path = None

        try:
            with transaction(write=True):
                record = ProjectFileRepository.get_file(file_id)

                if record is None:
                    raise ValueError("Archivo no encontrado.")

                ProjectAccessPolicy.require_writable(
                    record["project_id"]
                )

                path = (
                    UPLOAD_ROOT
                    / str(record["project_id"])
                    / record["stored_name"]
                )

                if path.exists():
                    staged_path = path.with_name(
                        f".{path.name}.{uuid4().hex}.deleting"
                    )
                    path.replace(staged_path)

                ProjectFileRepository.delete_file(file_id)
        except Exception:
            if staged_path and staged_path.exists() and path:
                staged_path.replace(path)
            raise

        if staged_path and staged_path.exists():
            try:
                staged_path.unlink()
            except OSError:
                # The database operation succeeded. A hidden staged file is
                # safer than restoring a file whose record no longer exists.
                pass

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
