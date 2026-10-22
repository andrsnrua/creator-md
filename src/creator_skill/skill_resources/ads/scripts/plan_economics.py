"""Techos publicitarios condicionales por cliente nuevo en su primera compra."""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import re


MONEY_FIELDS = (
    "net_revenue_per_new_customer",
    "variable_cost_per_new_customer",
    "reserve_per_new_customer",
    "non_ad_acquisition_cost_per_new_customer",
)
LEAD_FIELDS = {"lead_to_customer_rate", "lead_handling_cost"}
REQUIRED = {"currency", "basis", *MONEY_FIELDS}


def number(data: dict, field: str) -> Decimal:
    value = data[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} debe ser un número finito no negativo.")
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} debe ser un número finito no negativo.")
    return result


def json_number(value: Decimal) -> float:
    result = float(value)
    if not math.isfinite(result) or (result == 0 and value != 0):
        raise ValueError("El resultado excede el intervalo numérico admitido; revisa las unidades.")
    return result


def calculate(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Introduce un objeto JSON para un escenario, moneda y primera compra.")
    missing = REQUIRED - data.keys()
    unknown = data.keys() - REQUIRED - LEAD_FIELDS
    if missing:
        raise ValueError("Faltan campos: " + ", ".join(sorted(missing)))
    if unknown:
        raise ValueError("Campos no admitidos (no mezclar LTV, periodos o unidades): " + ", ".join(sorted(unknown)))
    if not isinstance(data["currency"], str) or not re.fullmatch(r"[A-Z]{3}", data["currency"]):
        raise ValueError("currency debe ser un código de una sola moneda, en tres letras mayúsculas; por ejemplo PEN.")
    if data["basis"] not in ("historical", "hypothesis"):
        raise ValueError('basis debe ser "historical" o "hypothesis".')
    if LEAD_FIELDS.intersection(data) and not LEAD_FIELDS.issubset(data):
        raise ValueError("lead_to_customer_rate y lead_handling_cost deben aparecer juntos; no se presume atención gratuita.")

    values = {key: number(data, key) for key in MONEY_FIELDS}
    warnings = []
    with localcontext() as context:
        context.prec = 40
        contribution = values["net_revenue_per_new_customer"] - values["variable_cost_per_new_customer"]
        cac = contribution - values["reserve_per_new_customer"] - values["non_ad_acquisition_cost_per_new_customer"]
        result = {
            "currency": data["currency"],
            "basis": data["basis"],
            "unit": "new_customer_first_purchase",
            "contribution_before_ads_per_new_customer": json_number(contribution),
            "ad_cac_ceiling": json_number(cac),
            "positive_ad_cac_allowance": cac > 0,
            "ad_cpl_ceiling": None,
            "positive_ad_cpl_allowance": None,
            "lead_economics_status": "not_requested",
        }
        if cac < 0:
            warnings.append("Techo CAC negativo: existe un déficit respecto a la reserva y costos declarados, incluso antes de pagar publicidad.")
        elif cac == 0:
            warnings.append("Techo CAC cero: no hay capacidad para un costo publicitario positivo bajo estos supuestos.")
        if LEAD_FIELDS.issubset(data):
            rate = number(data, "lead_to_customer_rate")
            handling = number(data, "lead_handling_cost")
            if rate > 1:
                raise ValueError("lead_to_customer_rate debe estar entre 0 y 1; 10% se escribe 0.1.")
            cpl = cac * rate - handling
            result.update({
                "lead_to_customer_rate": json_number(rate),
                "lead_handling_cost": json_number(handling),
                "ad_cpl_ceiling": json_number(cpl),
                "positive_ad_cpl_allowance": rate > 0 and cpl > 0,
                "lead_economics_status": (
                    "no_expected_customers" if rate == 0 else
                    "positive_ad_allowance" if cpl > 0 else "no_positive_ad_allowance"
                ),
            })
            if rate == 0:
                warnings.append("Tasa cero: no hay clientes esperados en este escenario; un CPL aritmético de cero no demuestra factibilidad.")
            elif cpl < 0:
                warnings.append("Techo CPL negativo: la atención consume más que el importe disponible por lead; el déficit se conserva.")
            elif cpl == 0:
                warnings.append("Techo CPL cero: no hay capacidad para pagar publicidad por lead bajo estos supuestos.")
    result["warnings"] = warnings
    result["limits"] = (
        "Unidades: una primera compra de un cliente nuevo y una sola moneda. "
        "La atención por lead debe estar excluida de los otros costos; el script no puede comprobar duplicaciones contables. "
        "Historical o hypothesis es una declaración del operador, no una validación de datos. "
        "Son techos condicionales, no presupuesto recomendado, pronóstico de beneficios ni resultados que una plataforma conseguirá. "
        "La contribución no es beneficio neto: faltan costos fijos e impuestos no incluidos."
    )
    return result


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Campo JSON repetido: {key}")
        result[key] = value
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON de un escenario; basis: historical o hypothesis; importes en una moneda")
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)
        print(json.dumps(calculate(data), ensure_ascii=False, allow_nan=False, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
