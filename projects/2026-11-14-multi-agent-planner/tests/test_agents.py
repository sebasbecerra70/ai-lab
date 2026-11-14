import json
from pathlib import Path

import pytest

from agent_team import MockLLM, Scratchpad, ToolError, Toolbox, parse_json, safe_eval, solve

FACTS = json.loads((Path(__file__).resolve().parent.parent / "data" / "facts.json").read_text())
TASK = "Add 120 servers: racks, power, cost, recommendation?"


def test_safe_eval_arithmetic_and_functions():
    assert safe_eval("ceil(120 * 0.45 / 12)") == 5
    assert safe_eval("max(a, b) - 1", {"a": 3, "b": 7}) == 6


@pytest.mark.parametrize("expr", ["__import__('os').system('ls')", "open('x')", "a.b", "1/0", "unknown + 1"])
def test_safe_eval_rejects_unsafe_or_bad_input(expr):
    with pytest.raises(ToolError):
        safe_eval(expr)


def test_toolbox_lookup_and_calc_see_facts():
    tb = Toolbox(FACTS)
    assert tb.lookup("pue") == 1.4
    assert tb.calc("servers * server_power_kw", {"servers": 10}) == pytest.approx(4.5)
    with pytest.raises(ToolError):
        tb.lookup("nonexistent")


def test_scratchpad_latest_and_render_filter():
    pad = Scratchpad()
    pad.add(1, "planner", "plan", "a -> b")
    pad.add(1, "critic", "critique", "missing c")
    pad.add(2, "planner", "plan", "a -> b -> c")
    assert pad.latest("plan").content == "a -> b -> c"
    assert pad.render({"critique"}) == "[r1 critic:critique] missing c"


def test_parse_json_tolerates_prose_and_fences():
    assert parse_json('Here you go:\n```json\n{"verdict": "approve"}\n```') == {"verdict": "approve"}
    with pytest.raises(ValueError):
        parse_json("no json here")


def test_critic_loop_fixes_power_oversight():
    out = solve(TASK, {"servers": 120}, FACTS, MockLLM())
    assert out.approved and out.rounds == 2
    assert out.results["racks_needed"] == 5  # power-bound, not the 3 racks space alone suggests
    assert out.results["power_shortfall_kw"] == pytest.approx(35.6)
    assert out.pad.latest("critique").round == 1
    assert out.usage.calls == {"planner": 2, "writer": 2, "critic": 2}


def test_answer_numbers_come_from_results():
    out = solve(TASK, {"servers": 120}, FACTS, MockLLM())
    for key in ("racks_needed", "servers_now"):
        assert f"{out.results[key]:.0f}" in out.answer


def test_tool_errors_block_approval_without_calling_the_critic():
    class BrokenPlanner(MockLLM):
        def complete(self, system, prompt):
            if "ROLE: planner" in system:
                return json.dumps({"steps": [{"id": "x", "tool": "calc", "expr": "servers / 0"},
                                             {"id": "d", "tool": "draft", "expr": ""}]})
            return super().complete(system, prompt)
    out = solve(TASK, {"servers": 120}, FACTS, BrokenPlanner(), max_rounds=2)
    assert not out.approved
    assert "critic" not in out.usage.calls
    assert "division by zero" in out.pad.latest("critique").content
    assert out.pad.latest("note").author == "orchestrator"


def test_invalid_plan_is_rejected():
    class DupPlanner:
        def complete(self, system, prompt):
            return '{"steps": [{"id": "a", "tool": "calc", "expr": "1"}, {"id": "a", "tool": "shell", "expr": "rm"}]}'
    with pytest.raises(ValueError, match="invalid plan"):
        solve(TASK, {"servers": 1}, FACTS, DupPlanner())


def test_small_deployment_fits_existing_power():
    out = solve(TASK, {"servers": 40}, FACTS, MockLLM())
    assert out.results["power_shortfall_kw"] == 0
    assert out.results["racks_needed"] == 2
