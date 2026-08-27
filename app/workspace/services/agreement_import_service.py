import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import token_urlsafe
from typing import Any
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.database.transaction import transaction
from app.storage import upload_path
from app.workspace.connectors.agreement_workbook_parser import (
    AgreementWorkbookError,
    AgreementWorkbookParser,
)
from app.workspace.repositories.agreement_document_repository import (
    AgreementDocumentRepository,
)
from app.workspace.repositories.agreement_item_repository import (
    AgreementItemRepository,
)
from app.workspace.repositories.agreement_repository import AgreementRepository
from app.workspace.repositories.customer_repository import CustomerRepository
from app.workspace.services.agreement_import_validator import AgreementImportValidator


logger = logging.getLogger(__name__)
STAGING_ROOT = upload_path("agreement-imports")
AGREEMENT_ROOT = upload_path("agreements")


class AgreementImportError(ValueError):
    pass


class AgreementImportService:
    MAX_UPLOAD_BYTES = 10 * 1024 * 1024
    TOKEN_TTL = timedelta(hours=2)

    @classmethod
    def get_document(cls, customer_id: int) -> tuple[dict[str, Any], Path]:
        agreements = AgreementRepository.list_customer_agreements(customer_id)
        if not agreements:
            raise AgreementImportError("El acuerdo no existe.")
        agreement = agreements[0]
        document = AgreementDocumentRepository.get_for_agreement(agreement["id"])
        if not document:
            raise AgreementImportError("El archivo del acuerdo no existe.")
        path = AGREEMENT_ROOT / str(agreement["id"]) / document["stored_name"]
        if not path.exists():
            raise AgreementImportError("El archivo del acuerdo no está disponible.")
        return document, path

    @classmethod
    def stage(cls, customer_id: int, file: FileStorage,
              metadata: dict[str, Any]) -> str:
        if CustomerRepository.get_customer(customer_id) is None:
            raise AgreementImportError("La cuenta no existe.")
        filename = secure_filename(file.filename or "")
        extension = Path(filename).suffix.lower()
        if not filename or extension not in {".xls", ".xlsx"}:
            raise AgreementImportError("Seleccione un archivo .xls o .xlsx válido.")
        file.stream.seek(0, 2)
        size = file.stream.tell()
        file.stream.seek(0)
        if size > cls.MAX_UPLOAD_BYTES:
            raise AgreementImportError("El archivo supera el límite de 10 MB.")
        token = token_urlsafe(32)
        STAGING_ROOT.mkdir(parents=True, exist_ok=True)
        workbook_path = STAGING_ROOT / f"{token}{extension}"
        state_path = cls._state_path(token)
        try:
            file.save(workbook_path)
            parsed = AgreementWorkbookParser.inspect(workbook_path)
            detected = parsed.get("detected_metadata", {})
            for field in (
                "supplier", "currency", "start_date", "end_date",
                "agreement_type",
            ):
                if not str(metadata.get(field) or "").strip() and detected.get(field):
                    metadata[field] = detected[field]
            state = {
                "token": token, "customer_id": customer_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "original_name": filename, "mime_type": file.mimetype,
                "file_extension": extension,
                "metadata": metadata,
                "selected_worksheet": parsed["selected_worksheet"],
                "mapping": parsed["mapping"], "consumed": False,
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            return token
        except AgreementWorkbookError:
            workbook_path.unlink(missing_ok=True)
            state_path.unlink(missing_ok=True)
            raise
        except Exception:
            workbook_path.unlink(missing_ok=True)
            state_path.unlink(missing_ok=True)
            raise

    @classmethod
    def preview(cls, customer_id: int, token: str, *, worksheet: str | None = None,
                mapping: dict[str, str] | None = None,
                metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        state = cls._load(customer_id, token)
        selected = worksheet or state["selected_worksheet"]
        parsed = AgreementWorkbookParser.inspect(
            cls._workbook_path(token, state["file_extension"]), selected
        )
        worksheet_changed = selected != state["selected_worksheet"]
        selected_mapping = (
            mapping if mapping is not None
            else parsed["mapping"] if worksheet_changed
            else state["mapping"]
        )
        if metadata is not None:
            state["metadata"].update(metadata)
        state.update(selected_worksheet=selected, mapping=selected_mapping)
        cls._save(state)
        validation = AgreementImportValidator.validate(state["metadata"], parsed, selected_mapping)
        customer = CustomerRepository.get_customer(customer_id)
        active = AgreementRepository.get_active_for_customer(customer_id)
        return {"state": state, "parsed": parsed, "validation": validation,
                "customer": customer, "active_agreement": active,
                "destinations": AgreementImportValidator.DESTINATIONS,
                "destination_labels": AgreementImportValidator.DESTINATION_LABELS,
                "preview_rows": validation["rows"][:100]}

    @classmethod
    def confirm(cls, customer_id: int, token: str, *, replace_active: bool) -> int:
        page = cls.preview(customer_id, token)
        state, validation = page["state"], page["validation"]
        if state.get("consumed"):
            raise AgreementImportError("Esta importación ya fue confirmada.")
        if not validation["can_confirm"]:
            raise AgreementImportError("Corrija los errores antes de confirmar.")
        active = page["active_agreement"]
        if active and not replace_active:
            raise AgreementImportError("Ya existe un acuerdo activo. Confirme expresamente su reemplazo.")
        state["consumed"] = True
        cls._save(state)
        destination = None
        agreement_id = None
        try:
            with transaction(write=True):
                if active:
                    AgreementRepository.expire(active["id"])
                metadata = state["metadata"]
                agreement_id = AgreementRepository.create_agreement(
                    customer_id=customer_id, name=metadata["name"], status="active",
                    supplier=metadata["supplier"], start_date=metadata["start_date"],
                    end_date=metadata["end_date"], notes=metadata.get("notes"),
                    currency=metadata["currency"],
                    agreement_type=metadata.get("agreement_type"),
                )
                folder = AGREEMENT_ROOT / str(agreement_id)
                folder.mkdir(parents=True, exist_ok=True)
                extension = state["file_extension"]
                stored_name = f"{uuid4().hex}{extension}"
                destination = folder / stored_name
                shutil.copy2(cls._workbook_path(token, extension), destination)
                AgreementDocumentRepository.create(
                    agreement_id, state["original_name"], stored_name,
                    state.get("mime_type"), destination.stat().st_size,
                    extension,
                )
                rows = [row for row in validation["rows"]
                        if row["status"] != "error" and not row["duplicate"]]
                AgreementItemRepository.insert_imported_items(
                    agreement_id, rows, state["original_name"]
                )
        except Exception:
            if destination:
                destination.unlink(missing_ok=True)
            state["consumed"] = False
            cls._save(state)
            raise
        try:
            cls.cancel(customer_id, token, allow_consumed=True)
        except OSError:
            logger.warning("No fue posible limpiar el artefacto temporal %s", token)
        return int(agreement_id)

    @classmethod
    def cancel(cls, customer_id: int, token: str, *, allow_consumed: bool = False) -> None:
        state = cls._load(customer_id, token, allow_consumed=allow_consumed)
        cls._workbook_path(token, state["file_extension"]).unlink(missing_ok=True)
        cls._state_path(token).unlink(missing_ok=True)

    @classmethod
    def _load(cls, customer_id: int, token: str,
              *, allow_consumed: bool = False) -> dict[str, Any]:
        if not token or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in token):
            raise AgreementImportError("El token de importación no es válido.")
        path = cls._state_path(token)
        if not path.exists():
            raise AgreementImportError("La importación expiró o no existe.")
        state = json.loads(path.read_text(encoding="utf-8"))
        created = datetime.fromisoformat(state["created_at"])
        if datetime.now(timezone.utc) - created > cls.TOKEN_TTL:
            cls._workbook_path(token, state["file_extension"]).unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            raise AgreementImportError("La importación expiró.")
        if state["customer_id"] != customer_id:
            raise AgreementImportError("La importación no pertenece a esta cuenta.")
        if state.get("consumed") and not allow_consumed:
            raise AgreementImportError("Esta importación ya fue confirmada.")
        return state

    @staticmethod
    def _state_path(token: str) -> Path: return STAGING_ROOT / f"{token}.json"
    @staticmethod
    def _workbook_path(token: str, extension: str) -> Path:
        return STAGING_ROOT / f"{token}{extension}"
    @classmethod
    def _save(cls, state: dict[str, Any]) -> None:
        cls._state_path(state["token"]).write_text(json.dumps(state), encoding="utf-8")
