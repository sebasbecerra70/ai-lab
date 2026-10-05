import json
from pathlib import Path

import pytest

from tool_agent import (Agent, KeywordPlannerLLM, ScriptedLLM, ToolError, calculate, convert_units,
                        default_registry, text_turn, tool_turn)

FACTS = Path(__file__).resolve().parent.parent / "data" / "ops_facts.json"


@pytest.fixture
def registry():
    return default_registry(FACTS)


def test_calculator_handles_precedence_and_rejects_code():
    assert calculate("(2400 - 1840) / 220") == pytest.approx(2.545455)
    with pytest.raises(ToolError):
        calculate("__import__('os').system('ls')")
    with pytest.raises(ToolError):
        calculate("1 / 0")


@pytest.mark.parametrize("value, src, dst, expected", [
    (1, "kW", "BTU/h", 3412.1416), (1000, "kW", "MW", 1.0),
    (3516.8528, "W", "ton", 1.0), (27, "C", "F", 80.6), (10, "gal", "L", 37.8541),
])
def test_unit_conversions(value, src, dst, expected):
    assert convert_units(value, src, dst) == pytest.approx(expected, rel=1e-4)


def test_conversion_across_dimensions_is_rejected():
    with pytest.raises(ToolError):
        convert_units(1, "kW", "gal")


def test_schema_validation_reports_errors_instead_of_raising(registry):
    content, is_error = registry.dispatch("lookup", {})
    assert is_error and "missing required argument 'key'" in content
    content, is_error = registry.dispatch("convert_units", {"value": "5", "from_unit": "kW", "to_unit": "W"})
    assert is_error and "must be number" in content
    content, is_error = registry.dispatch("rm_rf", {})
    assert is_error and "unknown tool" in content


def test_specs_match_messages_api_shape(registry):
    names = {s["name"] for s in registry.specs()}
    assert names == {"calculator", "lookup", "convert_units"}
    assert all(s["input_schema"]["type"] == "object" for s in registry.specs())


def test_loop_feeds_tool_results_back_and_returns_answer(registry):
    llm = ScriptedLLM([
        tool_turn("lookup", {"key": "hall_b.it_load_kw"}, "a"),
        tool_turn("convert_units", {"value": 1215, "from_unit": "kW", "to_unit": "ton"}, "b"),
        text_turn("Hall B needs about 345.5 tons of cooling."),
    ])
    result = Agent(llm, registry).run("cooling tons for hall B?")
    assert result.answer.startswith("Hall B needs")
    assert [s.tool for s in result.steps] == ["lookup", "convert_units"]
    last_user = llm.seen[2][-1]
    assert last_user["content"][0]["tool_use_id"] == "b"
    assert json.loads(last_user["content"][0]["content"]) == pytest.approx(345.4778, rel=1e-4)


def test_tool_error_is_returned_to_model_so_it_can_recover(registry):
    llm = ScriptedLLM([
        tool_turn("lookup", {"key": "hall_c.it_load_kw"}, "a"),
        tool_turn("lookup", {"key": "hall_a.it_load_kw"}, "b"),
        text_turn("Hall A draws 1840 kW."),
    ])
    result = Agent(llm, registry).run("hall c load?")
    assert result.steps[0].is_error and "Similar keys" in result.steps[0].result
    assert llm.seen[1][-1]["content"][0]["is_error"] is True
    assert not result.steps[1].is_error


def test_max_steps_guard_stops_a_looping_model(registry):
    looping = ScriptedLLM([tool_turn("calculator", {"expression": "1+1"}, f"c{i}") for i in range(20)])
    result = Agent(looping, registry, max_steps=3).run("loop forever")
    assert result.stopped_by_guard
    assert len(result.steps) == 3


def test_invalid_max_steps(registry):
    with pytest.raises(ValueError):
        Agent(ScriptedLLM([]), registry, max_steps=0)


def test_keyword_planner_end_to_end(registry):
    result = Agent(KeywordPlannerLLM(), registry).run(
        "Generator runtime in hours = site.diesel_tank_liters / site.generator_burn_lph")
    assert [s.tool for s in result.steps] == ["lookup", "lookup", "calculator"]
    assert "146.341463" in result.answer
