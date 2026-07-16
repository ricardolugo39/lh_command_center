from app.workspace.repositories.agreement_repository import (
    AgreementRepository,
)


class AgreementService:

    @staticmethod
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
    def update(
        **kwargs,
    ):
        AgreementRepository.update_agreement(
            **kwargs
        )

    @staticmethod
    def delete(
        agreement_id: int,
    ):
        AgreementRepository.delete_agreement(
            agreement_id
        )