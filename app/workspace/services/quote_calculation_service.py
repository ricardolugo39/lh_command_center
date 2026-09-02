from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Any

from app.workspace.repositories.quote_management_repository import (
    QuoteManagementRepository,
)


ZERO = Decimal("0")
CENT = Decimal("0.01")
PRODUCT_FACTORS = {
    "SCREW": Decimal("0.65"), "NUT": Decimal("0.60"),
    "BLOCK": Decimal("0.55"), "BRG": Decimal("0.75"),
    "RAIL": Decimal("0.60"), "REDUCER": Decimal("0.75"),
}


def money(value: Any) -> Decimal:
    return Decimal(str(value or "0")).quantize(CENT, rounding=ROUND_HALF_UP)


def decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception as error:
        raise ValueError("Valor numérico no válido.") from error


class QuoteCalculationService:
    @staticmethod
    def shipping(profile_id: int, weight: Decimal, zone: int, premium: str | None):
        if weight <= ZERO:
            raise ValueError("El peso total debe ser mayor que cero.")
        if weight <= Decimal("10"):
            chargeable = (weight * 2).to_integral_value(rounding=ROUND_CEILING) / 2
            rate = QuoteManagementRepository.exact_rate(
                profile_id, str(chargeable), zone
            )
            if rate is None:
                raise ValueError("No existe tarifa DHL para el peso calculado.")
            base = money(rate)
        else:
            increment = QuoteManagementRepository.increment_rate(
                profile_id, str(weight), zone
            )
            if not increment:
                raise ValueError("El peso excede el perfil DHL configurado.")
            step = decimal_value(increment["increment_kg"])
            start = Decimal("10") if step == Decimal("0.5") else (
                Decimal("30") if weight <= Decimal("70") else (
                    Decimal("70") if weight <= Decimal("300") else Decimal("300")
                )
            )
            chargeable = start + (
                (weight - start) / step
            ).to_integral_value(rounding=ROUND_CEILING) * step
            base_rate = QuoteManagementRepository.exact_rate(
                profile_id, str(start), zone
            )
            if base_rate is None:
                raise ValueError("Falta la tarifa DHL base del incremento.")
            increments = ((chargeable - start) / step).to_integral_value()
            base = money(decimal_value(base_rate) + increments * decimal_value(increment["rate_usd"]))
        settings = QuoteManagementRepository.settings()
        surcharge = money(settings.get(f"premium_{premium}_usd")) if premium else ZERO
        return chargeable, base, money(base + surcharge)

    @classmethod
    def calculate(cls, quote: dict[str, Any], lines: list[dict[str, Any]]):
        if not lines:
            raise ValueError("La cotización requiere al menos una línea.")
        profile = QuoteManagementRepository.active_profile()
        if not profile:
            raise ValueError("No existe un perfil DHL activo.")
        mapping = QuoteManagementRepository.resolve_zone(
            profile["id"], quote.get("origin_country_code") or "",
            quote.get("origin_service_area_code"),
        )
        if not mapping:
            raise ValueError("Seleccione un país y área de origen DHL configurados.")
        work = []
        for index, line in enumerate(lines, start=1):
            quantity = decimal_value(line.get("quantity"))
            fob_unit = decimal_value(line.get("vendor_fob_unit_usd"))
            unit_weight = decimal_value(line.get("unit_weight_kg"))
            if quantity <= ZERO or fob_unit <= ZERO or unit_weight <= ZERO:
                raise ValueError(f"Cantidad, FOB y peso deben ser positivos en la línea {index}.")
            if not str(line.get("lead_time") or "").strip():
                raise ValueError(f"Falta el tiempo de entrega en la línea {index}.")
            fob = money(quantity * fob_unit)
            # The worksheet uses a 1.6 packing/chargeable-weight factor before
            # consulting DHL and before evaluating the 50 kg customs threshold.
            weight = quantity * unit_weight * Decimal("1.6")
            work.append({**line, "quantity_d": quantity, "fob": fob, "weight": weight})
        total_fob = sum((line["fob"] for line in work), ZERO)
        total_weight = sum((line["weight"] for line in work), ZERO)
        chargeable, calculated_shipping, final_shipping = cls.shipping(
            profile["id"], total_weight, mapping["zone"], None
        )
        final_zone = mapping["zone"]
        if quote.get("manual_shipping_usd") not in (None, ""):
            final_shipping = money(quote["manual_shipping_usd"])
        settings = QuoteManagementRepository.settings()
        customs_applied = total_fob > Decimal("2000") or total_weight > Decimal("50")
        customs = Decimal("300.00") if customs_applied else ZERO
        bank = money(settings.get("bank_fee_usd", "30"))
        results = []
        allocated_shipping = allocated_customs = allocated_bank = ZERO
        for position, line in enumerate(work):
            last = position == len(work) - 1
            shipping = money(final_shipping * line["weight"] / total_weight) if not last else money(final_shipping - allocated_shipping)
            custom = money(customs * line["weight"] / total_weight) if not last else money(customs - allocated_customs)
            bank_part = money(bank * line["weight"] / total_weight) if not last else money(bank - allocated_bank)
            allocated_shipping += shipping
            allocated_customs += custom
            allocated_bank += bank_part
            landed = money(line["fob"] * Decimal("1.2") + shipping + custom + bank_part)
            custom_divisor = line.get("pricing_override_value")
            product_type = str(line.get("product_type") or "").upper()
            if product_type == "FREE":
                factor = decimal_value(custom_divisor)
                if factor <= ZERO or factor >= Decimal("1"):
                    raise ValueError(
                        f"El divisor libre de la línea {position + 1} debe ser mayor que 0 y menor que 1."
                    )
            else:
                factor = PRODUCT_FACTORS.get(product_type)
                if not factor:
                    raise ValueError(f"Seleccione el tipo de producto en la línea {position + 1}.")
            # Exact worksheet structure: FOB carries 20%, the product
            # component is divided by its profitability factor, freight
            # carries 70%, and bank/customs are passed through.
            selling_unit = money(
                (decimal_value(line.get("vendor_fob_unit_usd")) * Decimal("1.2") / factor)
                + (shipping * Decimal("1.7") + custom + bank_part) / line["quantity_d"]
            )
            selling_total = money(selling_unit * line["quantity_d"])
            profit = money(selling_total - landed)
            margin = money(profit / selling_total * 100) if selling_total else ZERO
            roi = money(profit / landed * 100) if landed else ZERO
            results.append({
                "id": line["id"], "shipping": str(shipping), "customs": str(custom),
                "bank": str(bank_part), "landed": str(landed),
                "selling_unit": str(selling_unit), "selling_total": str(selling_total),
                "profit": str(profit), "margin": str(margin), "roi": str(roi),
            })
        selling_total = sum((money(row["selling_total"]) for row in results), ZERO)
        landed_total = money(total_fob * Decimal("1.2") + final_shipping + customs + bank)
        profit = money(selling_total - landed_total)
        return {
            "quote": {
                "amount": float(selling_total),
                "normalized_amount": float(selling_total),
                "exchange_rate": 1,
                "estimated_trm": None,
                "calculated_dhl_zone": mapping["zone"], "final_dhl_zone": final_zone,
                "dhl_rate_profile_id": profile["id"], "actual_weight_kg": str(total_weight),
                "chargeable_weight_kg": str(chargeable),
                "calculated_shipping_usd": str(calculated_shipping),
                "final_shipping_usd": str(final_shipping), "customs_applied": int(customs_applied),
                "customs_base_cop": None, "customs_usd": str(customs),
                "bank_fee_usd": str(bank), "landed_cost_usd": str(landed_total),
                "profit_usd": str(profit),
                "margin_percent": str(money(profit / selling_total * 100) if selling_total else ZERO),
                "roi_percent": str(money(profit / landed_total * 100) if landed_total else ZERO),
            },
            "lines": results,
        }
