from app.workspace.repositories.agreement_repository import (
    AgreementRepository,
)
from app.database.transaction import transactional
from app.workspace.repositories.agreement_document_repository import AgreementDocumentRepository
from app.workspace.repositories.customer_repository import CustomerRepository
from app.workspace.constants.agreement_status import get_status_label
from app.workspace.services.agreement_analytics_service import AgreementAnalyticsService


class AgreementService:

    @staticmethod
    def get_customer_page(
        customer_id: int, *, search: str = "", status: str = "", page: int = 1
    ):
        customer = CustomerRepository.get_customer(customer_id)
        if customer is None:
            raise ValueError("La cuenta no existe.")
        agreements = AgreementRepository.list_customer_agreements(customer_id)
        agreement = agreements[0] if agreements else None
        document = None
        if agreement:
            agreement = {
                **agreement,
                "status": get_status_label(agreement.get("status")),
            }
            document = AgreementDocumentRepository.get_for_agreement(
                agreement["id"]
            )
        analytics = AgreementAnalyticsService.get_analytics(
            customer_id, agreements[0] if agreements else None,
            search=search, status=status, page=page,
        )
        items = analytics["products"] if analytics else []
        return {"customer": customer, "agreement": agreement,
                "items": items, "document": document, "analytics": analytics}

    @staticmethod
    @transactional
    def create(
        *,
        customer_id: int,
        agreement_number: str,
        name: str,
        status: str,
        agreement_type: str,
        supplier: str,
        annual_target: float | None,
        currency: str,
        start_date: str | None,
        end_date: str | None,
        renewal_date: str | None,
        has_consignment: bool,
        notes: str,
    ) -> int:

        if not name.strip():
            raise ValueError(
                "Agreement name is required."
            )

        return AgreementRepository.create_agreement(
            customer_id=customer_id,
            agreement_number=agreement_number,
            name=name,
            status=status,
            agreement_type=agreement_type,
            supplier=supplier,
            annual_target=annual_target,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
            renewal_date=renewal_date,
            has_consignment=has_consignment,
            notes=notes,
        )

    @staticmethod
    def get(
        agreement_id: int,
    ):
        return AgreementRepository.get_agreement(
            agreement_id
        )

    @staticmethod
    def list_customer(
        customer_id: int,
    ):
        return AgreementRepository.list_customer_agreements(
            customer_id
        )

    @staticmethod
    @transactional
    def update(
        **kwargs,
    ):
        AgreementRepository.update_agreement(
            **kwargs
        )

    @staticmethod
    @transactional
    def delete(
        agreement_id: int,
    ):
        AgreementRepository.delete_agreement(
            agreement_id
        )
