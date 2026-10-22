import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


RESOURCES = Path(__file__).resolve().parents[1] / "src/creator_skill/skill_resources/ads"
SCRIPT = RESOURCES / "scripts/plan_economics.py"
spec = importlib.util.spec_from_file_location("plan_economics", SCRIPT)
economics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(economics)


@pytest.fixture
def example():
    return json.loads((RESOURCES / "assets/examples/economia-servicio.json").read_text(encoding="utf-8"))


def test_service_economics_and_closing_rate_sensitivity(example):
    result = economics.calculate(example)
    assert result["contribution_before_ads_per_new_customer"] == 600
    assert result["ad_cac_ceiling"] == 350
    assert result["ad_cpl_ceiling"] == 30
    assert result["positive_ad_cpl_allowance"] is True
    assert result["basis"] == "hypothesis"
    assert economics.calculate(example | {"lead_to_customer_rate": .05})["ad_cpl_ceiling"] == 12.5


def test_negative_margins_and_reserves_preserve_deficit(example):
    result = economics.calculate(example | {"net_revenue_per_new_customer": 300})
    assert result["contribution_before_ads_per_new_customer"] == -100
    assert result["ad_cac_ceiling"] == -350
    assert result["ad_cpl_ceiling"] == -40
    assert result["positive_ad_cac_allowance"] is False
    assert result["positive_ad_cpl_allowance"] is False
    assert result["lead_economics_status"] == "no_positive_ad_allowance"
    assert result["warnings"]


@pytest.mark.parametrize("handling,cpl", [(0, 0), (5, -5)])
def test_zero_rate_is_not_a_feasible_free_acquisition_plan(example, handling, cpl):
    result = economics.calculate(example | {"lead_to_customer_rate": 0, "lead_handling_cost": handling})
    assert result["ad_cpl_ceiling"] == cpl
    assert result["positive_ad_cpl_allowance"] is False
    assert result["lead_economics_status"] == "no_expected_customers"
    assert any("no hay clientes esperados" in warning for warning in result["warnings"])


def test_zero_allowance_is_not_positive_and_decimal_rounding_does_not_create_a_deficit(example):
    data = example | {key: 0 for key in economics.MONEY_FIELDS}
    data.update(net_revenue_per_new_customer=.3, variable_cost_per_new_customer=.1,
                reserve_per_new_customer=.2, lead_handling_cost=0)
    result = economics.calculate(data)
    assert result["ad_cac_ceiling"] == 0
    assert result["ad_cpl_ceiling"] == 0
    assert result["positive_ad_cac_allowance"] is False
    assert result["positive_ad_cpl_allowance"] is False


def test_one_hundred_percent_closing_and_optional_lead_branch(example):
    result = economics.calculate(example | {"lead_to_customer_rate": 1})
    assert result["ad_cpl_ceiling"] == 345
    without_leads = {key: value for key, value in example.items() if key not in economics.LEAD_FIELDS}
    result = economics.calculate(without_leads)
    assert result["ad_cac_ceiling"] == 350
    assert result["ad_cpl_ceiling"] is None
    assert result["positive_ad_cpl_allowance"] is None
    assert result["lead_economics_status"] == "not_requested"


@pytest.mark.parametrize("field", [*economics.MONEY_FIELDS, "lead_to_customer_rate", "lead_handling_cost"])
@pytest.mark.parametrize("invalid", [True, -1, float("nan"), float("inf"), "100", None])
def test_rejects_invalid_numbers_in_every_financial_input(example, field, invalid):
    with pytest.raises(ValueError, match="número finito no negativo"):
        economics.calculate(example | {field: invalid})


@pytest.mark.parametrize("field", [*economics.REQUIRED, *economics.LEAD_FIELDS])
def test_missing_fields_do_not_silently_assume_zero_costs(example, field):
    example.pop(field)
    with pytest.raises(ValueError):
        economics.calculate(example)


@pytest.mark.parametrize("change", [
    {"currency": "PEN/USD"}, {"currency": ["PEN", "USD"]}, {"currency": True},
    {"basis": "unknown"}, {"basis": False}, {"lead_to_customer_rate": 10},
    {"ltv": 10000}, {"net_revenue_per_new_customer": {"PEN": 1000}},
])
def test_rejects_mixed_units_ambiguous_basis_ltv_and_percentage_inputs(example, change):
    with pytest.raises(ValueError):
        economics.calculate(example | change)


@pytest.mark.parametrize("data", [[], None, 100, "scenario"])
def test_rejects_inputs_that_are_not_a_single_scenario(data):
    with pytest.raises(ValueError, match="objeto JSON"):
        economics.calculate(data)


@pytest.mark.parametrize("changes", [
    {"net_revenue_per_new_customer": 0, "variable_cost_per_new_customer": 1e308,
     "reserve_per_new_customer": 1e308},
    {"net_revenue_per_new_customer": 1e-308, "variable_cost_per_new_customer": 0,
     "reserve_per_new_customer": 0, "non_ad_acquisition_cost_per_new_customer": 0,
     "lead_to_customer_rate": 1e-308, "lead_handling_cost": 0},
])
def test_numeric_limits_cannot_turn_results_into_infinity_or_a_false_zero(example, changes):
    with pytest.raises(ValueError, match="intervalo numérico"):
        economics.calculate(example | changes)


def test_cli_is_portable_and_fails_cleanly_for_duplicate_fields(tmp_path):
    process = subprocess.run([sys.executable, "-X", "utf8", "-I", str(SCRIPT),
                              str(RESOURCES / "assets/examples/economia-servicio.json")],
                             cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["ad_cpl_ceiling"] == 30
    invalid = tmp_path / "mixed.json"
    invalid.write_text('{"currency":"PEN","currency":"USD"}', encoding="utf-8")
    process = subprocess.run([sys.executable, "-X", "utf8", "-I", str(SCRIPT), str(invalid)],
                             cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert process.returncode == 2
    assert "Campo JSON repetido" in process.stderr
    assert "Traceback" not in process.stderr


def test_chat_example_uses_existing_cohort_calculator():
    from creator_skill.skill_ads_metrics import calculate
    data = json.loads((RESOURCES / "assets/examples/cohorte-chat.json").read_text(encoding="utf-8"))
    result = calculate(data)
    assert result["cost_per_conversation"] == 6
    assert result["conversation_to_sale_rate"] == .1
    assert result["cost_per_sale"] == 60
    assert result["contribution_after_ads"] == 0
