import hashlib
import json
import re
from datetime import date, datetime

from app.workspace.constants.commercial_office import canonical_sales_rep

class VisitNormalizer:
    GOOGLE_DATE_FORMAT = "%m/%d/%Y"
    GOOGLE_DATETIME_FORMATS = (
        "%m/%d/%Y", "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p",
    )
    IGNORED_SECTIONS = {
        "INFORMACIÓN GENERAL", "Seccion_Detalle_Visita", "Seccion_Seguimiento",
    }
    TYPE_MAP = {
        "comercial":"Comercial", "tecnica":"Técnica", "técnica":"Técnica",
        "seguimiento":"Seguimiento", "postventa":"Postventa",
        "post venta":"Postventa",
    }
    STATUS_MAP = {
        "abierto":"Abierto", "abierta":"Abierto",
        "en seguimiento":"En seguimiento", "seguimiento":"En seguimiento",
        "cerrado":"Cerrado", "cerrada":"Cerrado",
    }

    @classmethod
    def normalize(cls, row: dict) -> dict:
        source_id = cls._text(row.get("ID_Visita"))
        if not source_id:
            raise ValueError("ID_Visita es obligatorio.")
        warnings = []
        visit_date = cls._date(row.get("Fecha_Visita"), "Fecha_Visita", warnings)
        source_created = cls._datetime(row.get("Fecha_Registro"), "Fecha_Registro", warnings)
        raw_type = cls._text(row.get("Tipo_Visita"))
        visit_type = cls.TYPE_MAP.get(cls._key(raw_type), "Otro")
        if raw_type and visit_type == "Otro":
            warnings.append(f"Tipo de visita desconocido: {raw_type}")
        raw_status = cls._text(row.get("Estado"))
        visit_status = cls.STATUS_MAP.get(cls._key(raw_status), "Sin estado")
        if raw_status and visit_status == "Sin estado":
            warnings.append(f"Estado desconocido: {raw_status}")
        if visit_date and visit_date > date.today():
            warnings.append("Visita programada: la fecha informada es futura.")
        payload = {str(key): value for key, value in row.items()}
        normalized = {
            "source_visit_id":source_id,
            "source_created_at":source_created,
            "visit_date":visit_date.isoformat() if visit_date else None,
            "advisor_name":canonical_sales_rep(row.get("Asesor")),
            "customer_erp_id":cls.normalize_identifier(row.get("Cliente")),
            "source_customer_name":cls._text(row.get("Cliente_Nombre")),
            "visited_contact_name":cls._text(row.get("Contacto_Visitado")),
            "visited_contact_role":cls._text(row.get("Cargo_Contacto")),
            "visit_type":visit_type,"source_visit_type":raw_type,
            "visit_reason":cls._text(row.get("Motivo_Visita")),
            "executive_summary":cls._text(row.get("Resumen_Ejecutivo")),
            "detected_need":cls._text(row.get("Necesidad_Detectada")),
            "detected_risk":cls._text(row.get("Riesgo_Detectado")),
            "competitor":cls._text(row.get("Competencia_Presente")),
            "key_comments":cls._text(row.get("Comentarios_Clave")),
            "requires_action":cls._boolean(row.get("Requiere_Accion")),
            "required_action":cls._text(row.get("Accion_Requerida")),
            "follow_up_owner_name":canonical_sales_rep(
                row.get("Responsable_Seguimiento_nombre")
                or row.get("Responsable_Seguimiento")
            ),
            "commitment_date":cls._date_text(row.get("Fecha_Compromiso"), "Fecha_Compromiso", warnings),
            "generate_opportunity_requested":cls._boolean(row.get("Generar_Oportunidad_CRM")),
            "visit_status":visit_status,"source_visit_status":raw_status,
            "attachment_reference":cls._text(row.get("Adjuntos")),
            "source_payload_json":json.dumps(payload,ensure_ascii=False,sort_keys=True,default=str),
            "quality_warnings":warnings,
        }
        relevant = {key:value for key,value in normalized.items()
                    if key not in {"quality_warnings","source_payload_json"}}
        normalized["source_row_hash"] = hashlib.sha256(
            json.dumps(relevant,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        return normalized

    @staticmethod
    def normalize_identifier(value) -> str:
        return re.sub(r"[\s.\-,]", "", str("" if value is None else value).strip())

    @staticmethod
    def _text(value):
        text = str("" if value is None else value).strip()
        return text or None

    @staticmethod
    def _key(value) -> str:
        return str("" if value is None else value).strip().casefold()

    @staticmethod
    def _boolean(value) -> int:
        return int(VisitNormalizer._key(value) in {
            "true","1","si","sí","yes","x"
        })

    @classmethod
    def _date(cls, value, label, warnings):
        if not cls._text(value): return None
        try:
            return datetime.strptime(cls._text(value), cls.GOOGLE_DATE_FORMAT).date()
        except (ValueError,TypeError):
            raise ValueError(
                f"{label} debe usar el formato MM/DD/YYYY. Valor recibido: {value!r}."
            ) from None

    @classmethod
    def _date_text(cls, value, label, warnings):
        parsed = cls._date(value,label,warnings)
        return parsed.isoformat() if parsed else None

    @staticmethod
    def _datetime(value, label, warnings):
        if not VisitNormalizer._text(value): return None
        text = VisitNormalizer._text(value)
        for expected_format in VisitNormalizer.GOOGLE_DATETIME_FORMATS:
            try:
                return datetime.strptime(text, expected_format).isoformat()
            except (ValueError,TypeError):
                continue
        raise ValueError(
            f"{label} debe usar el formato MM/DD/YYYY, opcionalmente con hora. "
            f"Valor recibido: {value!r}."
        )
