import json
from math import ceil
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.database.transaction import transactional
from app.workspace.policies.commercial_approval_policy import CommercialApprovalPolicy
from app.workspace.repositories.commercial_approval_repository import CommercialApprovalRepository
from app.workspace.repositories.customer_repository import CustomerRepository
from app.workspace.repositories.project_repository import ProjectRepository
from app.workspace.repositories.project_brand_repository import ProjectBrandRepository
from app.workspace.repositories.customer_portfolio_repository import CustomerPortfolioRepository
from app.workspace.services.commercial_approval_events import CommercialApprovalEventPublisher
from app.workspace.services.opportunity_timeline_service import OpportunityTimelineService
from app.workspace.services.project_access_policy import ProjectAccessPolicy


class CommercialApprovalService:
    PAGE_SIZE = 25
    APPROVER_NAME = "Ricardo Lugo"
    MONEY_QUANTUM = Decimal("0.01")
    DISCOUNT_QUANTUM = Decimal("0.0001")
    REASONS = {
        "competition": "Competencia", "strategic_account": "Cuenta estratégica",
        "account_development": "Desarrollo de cuenta", "volume": "Oportunidad de volumen",
        "existing_agreement": "Acuerdo existente", "retention": "Retención de cliente",
        "technical": "Requerimiento técnico", "commercial_exception": "Excepción comercial",
        "other": "Otro",
    }

    @classmethod
    @transactional
    def create(cls, project_id: int, data: dict[str, Any], *, actor: str) -> int:
        project = ProjectAccessPolicy.require_writable(project_id)
        customer = CustomerRepository.get_customer(project["customer_id"])
        approval_type = CommercialApprovalRepository.get_type("commercial_discount")
        if not customer or not approval_type:
            raise ValueError("No fue posible preparar la solicitud comercial.")
        enriched = cls._enrich(project, customer, data)
        values = cls._validate(enriched, project)
        approval_id = CommercialApprovalRepository.create(
            project_id=project_id, approval_type_id=approval_type["id"],
            customer_name=customer["name"], opportunity_name=project["name"],
            created_by=actor, values=values,
        )
        CommercialApprovalRepository.add_history(
            approval_id=approval_id,event_type="created",actor=actor,
            from_status=None,to_status=CommercialApprovalPolicy.DRAFT,
            comments="Solicitud creada",event_data=json.dumps(values,ensure_ascii=False),
        )
        OpportunityTimelineService.publish_approval_event(
            event="created", approval={**values, "id":approval_id,
                                        "project_id":project_id},
            actor=actor)
        return approval_id

    @classmethod
    @transactional
    def update(cls, approval_id: int, data: dict[str, Any], *, actor: str) -> None:
        approval = cls._require(approval_id)
        ProjectAccessPolicy.require_writable(approval["project_id"])
        CommercialApprovalPolicy.require_editable(approval["status"])
        project = ProjectRepository.get_project(approval["project_id"])
        values = cls._validate(data, project)
        values["branch"] = approval.get("branch")
        for field in ("product_reference", "erp_price_source",
                      "erp_price_retrieved_at"):
            values[field] = approval.get(field)
        before = {field: approval.get(field) for field in CommercialApprovalRepository.FIELDS}
        CommercialApprovalRepository.update_draft(approval_id, values)
        CommercialApprovalRepository.add_history(
            approval_id=approval_id,event_type="edited",actor=actor,
            from_status=approval["status"],to_status=approval["status"],
            comments="Solicitud actualizada",
            event_data=json.dumps({"before":before,"after":values},ensure_ascii=False),
        )

    @classmethod
    @transactional
    def submit(cls, approval_id: int, *, actor: str) -> None:
        approval = cls._require(approval_id)
        ProjectAccessPolicy.require_writable(approval["project_id"])
        CommercialApprovalPolicy.require_transition(approval["status"], CommercialApprovalPolicy.SUBMITTED)
        cls._transition(approval_id, approval["status"], CommercialApprovalPolicy.SUBMITTED, actor, "Solicitud enviada")
        cls._transition(approval_id, CommercialApprovalPolicy.SUBMITTED, CommercialApprovalPolicy.PENDING, actor, "Pendiente de decisión")
        requested_values = None
        try:
            requested_values = cls.calculate_approved_values(
                list_unit_price=approval.get("list_price"),
                approved_discount_percent=approval.get("requested_discount"),
                quantity=approval.get("quantity"),
                currency=approval.get("currency"),
                requested_discount_percent=approval.get("requested_discount"))
        except ValueError:
            pass
        OpportunityTimelineService.publish_approval_event(
            event="submitted", approval=approval, actor=actor,
            monetary=requested_values)
        CommercialApprovalEventPublisher.publish("approval_submitted", {"approval_id":approval_id})

    @classmethod
    @transactional
    def decide(cls, approval_id: int, *, decision: str, approver: str,
               comments: str, approved_discount,
               expiration_date: str | None, role: str):
        CommercialApprovalPolicy.require_approver(role)
        approval = cls._require(approval_id)
        ProjectAccessPolicy.require_writable(approval["project_id"])
        if approval["status"] != CommercialApprovalPolicy.PENDING:
            raise ValueError("La solicitud no está pendiente de aprobación.")
        target = CommercialApprovalPolicy.DECISION_STATUS.get(decision)
        if not target:
            raise ValueError("Decisión comercial inválida.")
        if approver.strip().casefold() != cls.APPROVER_NAME.casefold():
            raise PermissionError("El aprobador autorizado es Ricardo Lugo.")
        comments = comments.strip()
        if not comments:
            raise ValueError("Los comentarios de la decisión son obligatorios.")
        monetary = None
        previous_amount = None
        new_amount = None
        if decision == "approved":
            approved_discount = (
                approved_discount if approved_discount not in (None, "")
                else approval["requested_discount"]
            )
            monetary = cls.calculate_approved_values(
                list_unit_price=approval.get("list_price"),
                approved_discount_percent=approved_discount,
                quantity=approval.get("quantity"),
                currency=approval.get("currency"),
                requested_discount_percent=approval.get("requested_discount"),
            )
            project_amount = ProjectRepository.get_commercial_amount(
                approval["project_id"]
            ) or {}
            if project_amount.get("commercial_amount") not in (None, ""):
                previous_amount = cls._decimal(
                    project_amount["commercial_amount"], "monto actual"
                )
            new_amount = Decimal(monetary["approved_total_amount"])
        CommercialApprovalRepository.add_decision(
            approval_id=approval_id,decision=decision,approver=approver,
            comments=comments,approved_discount=approved_discount,
            expiration_date=expiration_date or None,monetary=monetary,
        )
        CommercialApprovalPolicy.require_transition(approval["status"], target)
        CommercialApprovalRepository.update_status(approval_id,target)
        event_data = None
        if decision == "approved":
            event_data = json.dumps({
                "opportunity_amount_before":(
                    str(previous_amount) if previous_amount is not None else None
                ),
                "opportunity_amount_after":str(new_amount),
                "approval_id":approval_id,
            },ensure_ascii=False)
        CommercialApprovalRepository.add_history(
            approval_id=approval_id,event_type=target,actor=approver,
            from_status=approval["status"],to_status=target,
            comments=comments,event_data=event_data)
        if decision == "approved":
            ProjectRepository.update_commercial_amount(
                approval["project_id"], amount=monetary["approved_total_amount"],
                currency=monetary["currency"],
            )
        OpportunityTimelineService.publish_approval_event(
            event=decision, approval=approval, actor=approver,
            comments=comments, monetary=monetary,
            previous_amount=previous_amount)
        CommercialApprovalEventPublisher.publish(f"approval_{decision}", {"approval_id":approval_id})
        return monetary

    @classmethod
    @transactional
    def cancel(cls, approval_id: int, *, actor: str, comments: str) -> None:
        approval = cls._require(approval_id)
        ProjectAccessPolicy.require_writable(approval["project_id"])
        CommercialApprovalPolicy.require_transition(approval["status"], CommercialApprovalPolicy.CANCELLED)
        cls._transition(approval_id,approval["status"],CommercialApprovalPolicy.CANCELLED,actor,comments or "Solicitud cancelada")
        OpportunityTimelineService.publish_approval_event(
            event="cancelled", approval=approval, actor=actor,
            comments=comments)

    @classmethod
    @transactional
    def expire(cls, approval_id: int, *, actor: str, role: str) -> None:
        CommercialApprovalPolicy.require_approver(role)
        approval = cls._require(approval_id)
        ProjectAccessPolicy.require_writable(approval["project_id"])
        CommercialApprovalPolicy.require_transition(
            approval["status"], CommercialApprovalPolicy.EXPIRED
        )
        cls._transition(approval_id, approval["status"],
                        CommercialApprovalPolicy.EXPIRED, actor,
                        "Vigencia de aprobación finalizada")

    @classmethod
    def get_page(cls, project_id: int, *, status: str = "", page: int = 1):
        project = ProjectRepository.get_project(project_id)
        if not project:
            raise ValueError("La oportunidad no existe.")
        page = max(page,1)
        rows,total = CommercialApprovalRepository.list_project(
            project_id,status=status,limit=cls.PAGE_SIZE,offset=(page-1)*cls.PAGE_SIZE)
        return {"project":project,"approvals":[cls._present(row) for row in rows],
                "metrics":cls._metrics(CommercialApprovalRepository.get_metrics(project_id)),
                "status":status,"statuses":CommercialApprovalPolicy.LABELS,
                "pagination":{"page":page,"pages":max(1,ceil(total/cls.PAGE_SIZE)),"total":total},
                "is_read_only":ProjectAccessPolicy.is_read_only(project)}

    @classmethod
    def get_detail(cls, approval_id: int):
        approval = cls._require(approval_id)
        project = ProjectRepository.get_project(approval["project_id"])
        project_amount = ProjectRepository.get_commercial_amount(
            approval["project_id"]
        )
        impact = cls._build_impact(approval, project_amount)
        return {"approval":cls._present(approval),
                "history":[{**row,"from_label":CommercialApprovalPolicy.LABELS.get(row["from_status"],""),"to_label":CommercialApprovalPolicy.LABELS.get(row["to_status"],"")} for row in CommercialApprovalRepository.list_history(approval_id)],
                "decisions":CommercialApprovalRepository.list_decisions(approval_id),
                "impact":impact,
                "reasons":cls.REASONS,
                "is_read_only":ProjectAccessPolicy.is_read_only(ProjectRepository.get_project(approval["project_id"]))}

    @classmethod
    def get_summary(cls, project_id: int):
        latest = CommercialApprovalRepository.get_latest(project_id)
        return cls._present(latest) if latest else None

    @classmethod
    def calculate_approved_values(cls, *, list_unit_price,
                                  approved_discount_percent, quantity,
                                  currency, requested_discount_percent=None):
        if list_unit_price in (None, ""):
            raise ValueError("No es posible calcular el precio aprobado porque la solicitud no tiene un precio de lista válido.")
        if not str(currency or "").strip():
            raise ValueError("La moneda es obligatoria para aprobar la solicitud.")
        list_price = cls._decimal(list_unit_price, "precio de lista")
        discount = cls._decimal(approved_discount_percent, "descuento aprobado")
        qty = cls._decimal(quantity, "cantidad")
        if discount < 0 or discount > 100:
            raise ValueError("El descuento aprobado debe estar entre 0% y 100%.")
        if abs(discount.as_tuple().exponent) > 4:
            raise ValueError("El descuento aprobado permite máximo cuatro decimales.")
        if list_price <= 0:
            raise ValueError("No es posible calcular el precio aprobado porque la solicitud no tiene un precio de lista válido.")
        if qty <= 0:
            raise ValueError("La cantidad debe ser mayor que cero.")
        approved_unit = (list_price * (Decimal("1") - discount / Decimal("100"))).quantize(
            cls.MONEY_QUANTUM,rounding=ROUND_HALF_UP)
        if approved_unit < 0:
            raise ValueError("El precio final aprobado no puede ser negativo.")
        total = (approved_unit * qty).quantize(cls.MONEY_QUANTUM,rounding=ROUND_HALF_UP)
        requested = cls._decimal(requested_discount_percent or 0,"descuento solicitado")
        return {
            "requested_discount_percent":str(requested),
            "approved_discount_percent":str(discount),
            "list_unit_price":str(list_price.quantize(cls.MONEY_QUANTUM,rounding=ROUND_HALF_UP)),
            "approved_unit_price":str(approved_unit),"quantity":str(qty),
            "approved_total_amount":str(total),"currency":str(currency).upper(),
        }

    @staticmethod
    def _decimal(value, label):
        try:
            return Decimal(str(value))
        except (InvalidOperation,ValueError,TypeError):
            raise ValueError(f"El campo {label} debe ser numérico.") from None

    @classmethod
    def _build_impact(cls, approval, project):
        current = cls._decimal(
            project.get("commercial_amount"), "monto actual"
        ) if project and project.get("commercial_amount") not in (None, "") else None
        proposed = None
        try:
            proposed = cls.calculate_approved_values(
                list_unit_price=approval.get("list_price"),
                approved_discount_percent=approval.get("requested_discount"),
                quantity=approval.get("quantity"),
                currency=approval.get("currency"),
                requested_discount_percent=approval.get("requested_discount"),
            )
        except ValueError:
            pass
        return {
            "current_amount": str(current) if current is not None else None,
            "current_currency": project.get("commercial_currency") if current is not None else None,
            "proposed": proposed,
        }

    @classmethod
    def get_form_defaults(cls, project_id: int):
        project = ProjectRepository.get_project(project_id)
        if not project:
            raise ValueError("La oportunidad no existe.")
        customer = CustomerRepository.get_customer(project["customer_id"])
        return cls._enrich(project, customer, {})

    @staticmethod
    def _enrich(project, customer, data):
        enriched = dict(data)
        brands = ProjectBrandRepository.list_project_brands(project["id"])
        assignment = CustomerPortfolioRepository.get_assignment(
            (customer or {}).get("erp_customer_id") or ""
        ) or {}
        enriched["manufacturer"] = enriched.get("manufacturer") or (
            brands[0]["brand"] if brands else None)
        enriched["branch"] = assignment.get("office")
        current_amount = ProjectRepository.get_commercial_amount(project["id"])
        enriched["opportunity_value"] = enriched.get("opportunity_value") or (
            current_amount.get("commercial_amount") if current_amount else None
        )
        enriched["product_reference"] = enriched.get("product_reference") or enriched.get("product")
        enriched["competitor"] = enriched.get("competitor") or project.get("competitor_company")
        return enriched

    @classmethod
    def _validate(cls, data, project):
        reason = str(data.get("reason_code") or "").strip()
        justification = str(data.get("justification") or "").strip()
        if reason not in cls.REASONS:
            raise ValueError("Seleccione un motivo válido.")
        if not justification:
            raise ValueError("La justificación es obligatoria.")
        values = {field:data.get(field) for field in CommercialApprovalRepository.FIELDS}
        for field in ("quantity","opportunity_value","probability","list_price","requested_price","requested_discount","estimated_margin","expected_revenue","competitor_price"):
            raw = data.get(field)
            values[field] = str(cls._decimal(raw,field)) if raw not in (None,"") else None
        if values["requested_discount"] is None:
            if values["list_price"] and values["requested_price"] is not None:
                if Decimal(values["list_price"]) <= 0:
                    raise ValueError("El precio de lista debe ser mayor que cero.")
                values["requested_discount"] = str(
                    (Decimal(values["list_price"])-Decimal(values["requested_price"]))
                    / Decimal(values["list_price"])*Decimal("100"))
            else:
                raise ValueError("El descuento solicitado es obligatorio.")
        if not Decimal("0") <= Decimal(values["requested_discount"]) <= Decimal("100"):
            raise ValueError("El descuento debe estar entre 0% y 100%.")
        if abs(Decimal(values["requested_discount"]).as_tuple().exponent) > 4:
            raise ValueError("El descuento permite máximo cuatro decimales.")
        if values["quantity"] is not None and Decimal(values["quantity"]) <= 0:
            raise ValueError("La cantidad debe ser mayor que cero.")
        if values["list_price"] is not None and Decimal(values["list_price"]) <= 0:
            raise ValueError("El precio de lista debe ser mayor que cero.")
        currency = str(data.get("currency") or "").strip().upper()
        if not currency:
            raise ValueError("La moneda es obligatoria.")
        values.update(reason_code=reason,justification=justification,
                      current_stage=project["status"],
                      sales_representative=project.get("sales_rep"),
                      currency=currency)
        return values

    @staticmethod
    def _require(approval_id):
        approval = CommercialApprovalRepository.get(approval_id)
        if not approval:
            raise ValueError("La solicitud de aprobación no existe.")
        return approval

    @staticmethod
    def _transition(approval_id,current,target,actor,comments):
        CommercialApprovalPolicy.require_transition(current,target)
        CommercialApprovalRepository.update_status(approval_id,target,submitted=target==CommercialApprovalPolicy.SUBMITTED)
        CommercialApprovalRepository.add_history(approval_id=approval_id,event_type=target,actor=actor,from_status=current,to_status=target,comments=comments)

    @staticmethod
    def _present(row):
        if not row:return None
        return {**row,"number":f"AP-{int(row['id']):06d}",
                "status_label":CommercialApprovalPolicy.LABELS.get(row["status"],row["status"]),
                "reason_label":CommercialApprovalService.REASONS.get(row.get("reason_code"),row.get("reason_code")),
                "pending_since":row.get("submitted_at") if row.get("status")==CommercialApprovalPolicy.PENDING else None}

    @staticmethod
    def _metrics(row):
        return {"pending":int(row.get("pending") or 0),"approved":int(row.get("approved") or 0),
                "rejected":int(row.get("rejected") or 0),
                "average_discount":float(row.get("average_discount") or 0),
                "average_hours":float(row.get("average_hours") or 0)}
