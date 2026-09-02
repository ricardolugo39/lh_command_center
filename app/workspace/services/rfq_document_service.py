from pathlib import Path
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.storage import upload_path
from app.workspace.repositories.rfq_repository import RFQRepository


class RFQDocumentService:
    MAX_FILE_BYTES = 15 * 1024 * 1024
    ALLOWED_EXTENSIONS = {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg",
        ".jpeg", ".txt", ".zip",
    }

    @classmethod
    def validate(cls, uploads: list[FileStorage]) -> list[FileStorage]:
        clean = [upload for upload in uploads if upload and upload.filename]
        for upload in clean:
            filename = secure_filename(upload.filename or "")
            if not filename or Path(filename).suffix.lower() not in cls.ALLOWED_EXTENSIONS:
                raise ValueError(f"Tipo de archivo no permitido: {upload.filename}.")
            stream = upload.stream
            position = stream.tell()
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(position)
            if size > cls.MAX_FILE_BYTES:
                raise ValueError(f"{upload.filename} supera el límite de 15 MB.")
        return clean

    @classmethod
    def save_many(
        cls, rfq_id: int, uploads: list[FileStorage], uploaded_by_user_id: int,
    ) -> None:
        folder = upload_path("rfqs", str(rfq_id))
        folder.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        try:
            for upload in uploads:
                original = secure_filename(upload.filename or "archivo")
                extension = Path(original).suffix.lower()
                destination = folder / f"{uuid4().hex}{extension}"
                upload.save(destination)
                saved.append(destination)
                RFQRepository.add_document(rfq_id, {
                    "original_filename": original,
                    "stored_filename": str(destination),
                    "mime_type": upload.mimetype,
                    "size_bytes": destination.stat().st_size,
                    "uploaded_by_user_id": uploaded_by_user_id,
                })
        except Exception:
            for path in saved:
                path.unlink(missing_ok=True)
            raise
