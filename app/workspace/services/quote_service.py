from typing import Any

from app.workspace.repositories.quote_repository import (
    QuoteRepository,
)


VALID_CURRENCIES = {
    "COP",
    "USD",
}

VALID_EXCHANGE_RATE_TYPES = {
    "estimated",
    "final",
}


class QuoteService:

    @staticmethod
    def normalize_amount(
        *,
        amount: float,
        currency_code: str,
        exchange_rate: float | None = None,
    ) -> float:
        clean_currency = currency_code.strip().upper()

        if clean_currency not in VALID_CURRENCIES:
            raise ValueError(
                f"Invalid currency: {clean_currency}"
            )

        if amount < 0:
            raise ValueError(
                "Amount cannot be negative."
            )

        if clean_currency == "COP":
            return amount

        if exchange_rate is None:
            raise ValueError(
                "USD quotes require an exchange rate."
            )

        if exchange_rate <= 0:
            raise ValueError(
                "Exchange rate must be greater than zero."
            )

        return amount * exchange_rate

    @staticmethod
    def format_amount(
        *,
        amount: float | None,
        currency_code: str,
    ) -> str:
        if amount is None:
            return "—"

        clean_currency = currency_code.strip().upper()

        return (
            f"{clean_currency} "
            f"{amount:,.2f}"
        )

    @staticmethod
    def format_exchange_rate(
        exchange_rate: float | None,
    ) -> str:
        if exchange_rate is None:
            return "—"

        return f"COP {exchange_rate:,.2f} / USD"

    @staticmethod
    def exchange_rate_type_label(
        exchange_rate_type: str | None,
    ) -> str:
        labels = {
            "estimated": "Estimada",
            "final": "Final",
        }

        if exchange_rate_type is None:
            return "No aplica"

        return labels.get(
            exchange_rate_type,
            exchange_rate_type,
        )

    @staticmethod
    def enrich_quote(
        quote: dict[str, Any],
    ) -> dict[str, Any]:
        currency_code = (
            quote.get("currency_code")
            or "COP"
        ).upper()

        amount = quote.get("amount")
        normalized_amount = quote.get(
            "normalized_amount"
        )

        if (
            normalized_amount is None
            and amount is not None
        ):
            normalized_amount = (
                QuoteService.normalize_amount(
                    amount=amount,
                    currency_code=currency_code,
                    exchange_rate=quote.get(
                        "exchange_rate"
                    ),
                )
            )

        return {
            **quote,
            "currency_code": currency_code,
            "display_quote_number": (
                f"{quote['prefix']}-"
                f"{quote['quote_number']}"
            ),
            "display_amount": (
                QuoteService.format_amount(
                    amount=amount,
                    currency_code=currency_code,
                )
            ),
            "display_normalized_amount": (
                QuoteService.format_amount(
                    amount=normalized_amount,
                    currency_code="COP",
                )
            ),
            "display_exchange_rate": (
                QuoteService.format_exchange_rate(
                    quote.get("exchange_rate")
                )
            ),
            "exchange_rate_type_label": (
                QuoteService.exchange_rate_type_label(
                    quote.get(
                        "exchange_rate_type"
                    )
                )
            ),
        }

    @staticmethod
    def list_project_quotes(
        project_id: int,
    ) -> list[dict[str, Any]]:
        quotes = QuoteRepository.list_project_quotes(
            project_id
        )

        return [
            QuoteService.enrich_quote(quote)
            for quote in quotes
        ]

    @staticmethod
    def get_quote(
        quote_id: int,
    ) -> dict[str, Any] | None:
        quote = QuoteRepository.get_quote(
            quote_id
        )

        if quote is None:
            return None

        return QuoteService.enrich_quote(
            quote
        )

    @staticmethod
    def update_exchange_rate(
        *,
        quote_id: int,
        exchange_rate: float,
        exchange_rate_type: str,
    ) -> None:
        quote = QuoteRepository.get_quote(
            quote_id
        )

        if quote is None:
            raise ValueError(
                "Quote not found."
            )

        clean_rate_type = (
            exchange_rate_type.strip().lower()
        )

        if (
            clean_rate_type
            not in VALID_EXCHANGE_RATE_TYPES
        ):
            raise ValueError(
                "Invalid exchange rate type."
            )

        normalized_amount = (
            QuoteService.normalize_amount(
                amount=quote["amount"],
                currency_code=quote[
                    "currency_code"
                ],
                exchange_rate=exchange_rate,
            )
        )

        QuoteRepository.update_exchange_rate(
            quote_id=quote_id,
            exchange_rate=exchange_rate,
            exchange_rate_type=clean_rate_type,
            normalized_amount=normalized_amount,
        )

    @staticmethod
    def update_quote(
        *,
        quote_id: int,
        prefix: str,
        quote_number: str,
        quote_date: str | None,
        amount: float,
        currency_code: str,
        exchange_rate: float | None,
        exchange_rate_type: str | None,
        quote_status: str | None,
    ) -> dict[str, Any]:
        quote = QuoteRepository.get_quote(
            quote_id
        )

        if quote is None:
            raise ValueError(
                "La cotización no existe."
            )

        clean_prefix = prefix.strip().upper()
        clean_number = quote_number.strip()
        clean_currency = currency_code.strip().upper()

        if not clean_prefix:
            raise ValueError(
                "El prefijo es obligatorio."
            )

        if not clean_number:
            raise ValueError(
                "El número de cotización es obligatorio."
            )

        if clean_currency not in VALID_CURRENCIES:
            raise ValueError(
                "La moneda debe ser COP o USD."
            )

        if amount < 0:
            raise ValueError(
                "El valor no puede ser negativo."
            )

        clean_rate_type = None

        if clean_currency == "COP":
            exchange_rate = None
            normalized_amount = amount

        else:
            if exchange_rate is None or exchange_rate <= 0:
                raise ValueError(
                    "Las cotizaciones en USD requieren "
                    "una tasa de cambio mayor que cero."
                )

            clean_rate_type = (
                exchange_rate_type or ""
            ).strip().lower()

            if (
                clean_rate_type
                not in VALID_EXCHANGE_RATE_TYPES
            ):
                raise ValueError(
                    "Debe seleccionar si la tasa es "
                    "estimada o final."
                )

            normalized_amount = (
                QuoteService.normalize_amount(
                    amount=amount,
                    currency_code=clean_currency,
                    exchange_rate=exchange_rate,
                )
            )

        QuoteRepository.update_quote_details(
            quote_id=quote_id,
            prefix=clean_prefix,
            quote_number=clean_number,
            quote_date=quote_date,
            amount=amount,
            currency_code=clean_currency,
            exchange_rate=exchange_rate,
            exchange_rate_type=clean_rate_type,
            normalized_amount=normalized_amount,
            quote_status=quote_status,
        )

        updated_quote = QuoteService.get_quote(
            quote_id
        )

        if updated_quote is None:
            raise ValueError(
                "No fue posible recuperar la cotización."
            )

        return updated_quote