from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Any

from app.workspace.repositories.quote_management_repository import (
    QuoteManagementRepository,
)


ZERO = Decimal("0")
CENT = Decimal("0.01")


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
            weight = quantity * unit_weight
            work.append({**line, "quantity_d": quantity, "fob": fob, "weight": weight})
        total_fob = sum((line["fob"] for line in work), ZERO)
        total_weight = sum((line["weight"] for line in work), ZERO)
        chargeable, calculated_shipping, final_shipping = cls.shipping(
            profile["id"], total_weight, mapping["zone"], quote.get("premium_service")
        )
        final_zone = mapping["zone"]
        if quote.get("final_dhl_zone") and quote.get("zone_override_reason"):
            final_zone = int(quote["final_dhl_zone"])
            _, _, final_shipping = cls.shipping(
                profile["id"], total_weight, final_zone, quote.get("premium_service")
            )
        if quote.get("final_shipping_usd") and quote.get("shipping_override_reason"):
            final_shipping = money(quote["final_shipping_usd"])
        settings = QuoteManagementRepository.settings()
        customs_applied = total_fob > Decimal("2000") or total_weight > Decimal("50")
        customs = Decimal("300.00") if customs_applied else ZERO
        bank = money(settings.get("bank_fee_usd", "30"))
        results = []
        allocated_shipping = allocated_customs = allocated_bank = ZERO
        for position, line in enumerate(work):
            last = position == len(work) - 1
            shipping = money(final_shipping * line["weight"] / total_weight) if not last else money(final_shipping - allocated_shipping)
            custom = money(customs * line["fob"] / total_fob) if not last else money(customs - allocated_customs)
            bank_part = money(bank * line["fob"] / total_fob) if not last else money(bank - allocated_bank)
            allocated_shipping += shipping
            allocated_customs += custom
            allocated_bank += bank_part
            landed = money(line["fob"] + shipping + custom + bank_part)
            rule_value = line.get("pricing_override_value")
            if rule_value:
                selling_unit = money(rule_value)
            elif line.get("pricing_rule_id"):
                rule = QuoteManagementRepository.pricing_rule(int(line["pricing_rule_id"]))
                if not rule:
                    raise ValueError("La regla de precio seleccionada no está activa.")
                landed_unit = landed / line["quantity_d"]
                value = decimal_value(rule["default_value"])
                if rule["rule_type"] == "cost_multiplier":
                    selling_unit = money(landed_unit * value)
                elif rule["rule_type"] == "markup":
                    selling_unit = money(landed_unit * (Decimal("1") + value / 100))
                else:
                    if value >= 100:
                        raise ValueError("El margen bruto configurado debe ser menor a 100%.")
                    selling_unit = money(landed_unit / (Decimal("1") - value / 100))
            else:
                raise ValueError("Cada línea requiere una regla o precio manual autorizado.")
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
        landed_total = money(total_fob + final_shipping + customs + bank)
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
