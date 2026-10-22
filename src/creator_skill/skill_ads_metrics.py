"""Portable cohort arithmetic. Does not choose budgets or infer causal lift."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def calculate(data: dict) -> dict:
    if data.get("same_cohort") is not True:
        raise ValueError("Confirma same_cohort=true: gasto, conversaciones y ventas deben pertenecer a la misma cohorte y ventana.")
    if not data.get("currency") or not data.get("period"):
        raise ValueError("Indica moneda y periodo; no mezcles monedas o ventanas.")
    for key in ("spend", "conversations", "sales", "net_revenue", "variable_costs"):
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{key} debe ser un número finito no negativo.")
    for key in ("conversations", "sales"):
        if int(data[key]) != data[key]:
            raise ValueError(f"{key} debe ser un recuento entero.")
    if data["sales"] > data["conversations"]:
        raise ValueError("Este cálculo usa conversaciones únicas con venta, no pedidos repetidos por conversación.")
    spend, conversations, sales = (data[k] for k in ("spend", "conversations", "sales"))
    contribution = data["net_revenue"] - data["variable_costs"]
    warnings = []
    if not sales:
        warnings.append("Sin ventas observadas: CPA indefinido; no equivale a costo cero.")
    if not spend:
        warnings.append("Sin gasto: ROAS indefinido.")
    if data.get("cohort_mature") is not True:
        warnings.append("Cohorte no confirmada como madura: pueden faltar cierres o devoluciones.")
    return {"currency": data["currency"], "period": data["period"],
            "cost_per_conversation": spend / conversations if conversations else None,
            "conversation_to_sale_rate": sales / conversations if conversations else None,
            "cost_per_sale": spend / sales if sales else None,
            "roas": data["net_revenue"] / spend if spend else None,
            "contribution_before_ads": contribution,
            "contribution_after_ads": contribution - spend,
            "break_even_ad_cost_per_sale": contribution / sales if sales else None,
            "warnings": warnings,
            "limits": "Contribución antes de costos fijos e impuestos no incluidos por el usuario. No es beneficio neto, CAC de nuevos clientes ni atribución causal. El punto de equilibrio no reserva utilidad."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON de una cohorte comparable")
    args = parser.parse_args()
    try:
        print(json.dumps(calculate(json.loads(args.input.read_text(encoding="utf-8"))), ensure_ascii=False, indent=2))
    except ValueError as exc:
        parser.exit(2, str(exc) + "\n")
