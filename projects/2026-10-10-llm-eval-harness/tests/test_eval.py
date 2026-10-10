import json
from pathlib import Path

import pytest

from llm_eval import (Case, KeywordJudge, ReplayLLM, grade, grade_contains, grade_exact, grade_json_keys,
                      grade_llm_judge, grade_regex, load_cases, render, run)

DATA = Path(__file__).resolve().parent.parent / "data"


def test_exact_with_and_without_normalization():
    assert grade_exact("Shipped.", "shipped", normalize=True).passed
    assert not grade_exact("Shipped.", "shipped").passed


def test_contains_all_any_none():
    assert grade_contains("Refund within 30 days", all=["30 days"]).passed
    assert not grade_contains("Refund within 14 days", all=["30 days"]).passed
    assert not grade_contains("yes", any=["1 hour", "60 minutes"]).passed
    g = grade_contains("Yes, cash is fine", all=["cash"], none=["yes, cash"])
    assert not g.passed and "banned" in g.reason


def test_regex_with_forbidden_pattern():
    assert grade_regex("1Z999AA10123456784", r"^1Z[0-9A-Z]{16}$").passed
    assert not grade_regex("Tracking: 1Z999AA10123456784", r"^1Z[0-9A-Z]{16}$").passed
    assert not grade_regex("I can't, but code: ABCDE1", "can't", must_not=r"code:\s*[A-Z0-9]{5,}").passed


def test_json_keys():
    assert grade_json_keys('{"street": "a", "city": "b", "zip": "c"}', ["street", "city", "zip"]).passed
    assert "missing keys ['zip']" in grade_json_keys('{"street": "a", "city": "b"}', ["street", "city", "zip"]).reason
    assert not grade_json_keys("street: a", ["street"]).passed


def test_keyword_judge_scores_each_criterion():
    rubric = ["must apologize", "must give a next step or new estimate", "must be one sentence"]
    assert grade_llm_judge("Sorry for the delay, it will arrive Friday.", rubric, KeywordJudge()).passed
    g = grade_llm_judge("Your order is late. It will arrive Friday.", rubric, KeywordJudge())
    assert not g.passed and "#1" in g.reason and "#3" in g.reason and "#2" not in g.reason


def test_keyword_judge_handles_negated_must_not():
    rubric = ["must not suggest opening the package"]
    assert grade_llm_judge("Do not open it; evacuate.", rubric, KeywordJudge()).passed
    assert not grade_llm_judge("Open the box and check the cells.", rubric, KeywordJudge()).passed


def test_judge_with_bad_output_fails_closed():
    class Broken:
        def complete(self, system, prompt):
            return "I think it's fine"

    assert not grade_llm_judge("x", ["must apologize"], Broken()).passed

    class WrongCount:
        def complete(self, system, prompt):
            return json.dumps({"verdicts": [{"criterion": 1, "pass": True}]})

    assert "1 verdicts for 2 criteria" in grade_llm_judge("x", ["a", "b"], WrongCount()).reason


def test_unknown_grader_and_missing_judge_raise():
    with pytest.raises(ValueError):
        grade({"type": "vibes"}, "x")
    with pytest.raises(ValueError):
        grade({"type": "llm_judge", "rubric": ["a"]}, "x")


def test_runner_turns_grader_crash_into_failed_case():
    cases = [Case("bad", "q", {"type": "regex", "pattern": "("})]
    report = run(cases, ReplayLLM({"q": "anything"}))
    assert report.pass_rate == 0 and "grader error" in report.results[0].grade.reason


def test_duplicate_case_ids_rejected(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps([{"id": "a", "prompt": "x", "grader": {"type": "exact", "expected": "y"}}] * 2))
    with pytest.raises(ValueError):
        load_cases(p)


def test_sample_suite_report_regressions_and_gate():
    cases = load_cases(DATA / "cases.json")
    recorded = json.loads((DATA / "model_outputs.json").read_text())
    report = run(cases, ReplayLLM({c.prompt: recorded[c.id] for c in cases}), KeywordJudge())
    assert report.pass_rate == pytest.approx(9 / 12)
    assert report.by_tag()["format"] == (3, 3)
    baseline = json.loads((DATA / "baseline.json").read_text())
    assert report.diff(baseline["results"]) == (["sla-hours"], ["pii-refusal"])
    text, ok = render(report, baseline, gate=0.7)
    assert not ok and "regressions ['sla-hours']" in text  # a regression fails the gate even above threshold
    _, ok_no_baseline = render(report, None, gate=0.7)
    assert ok_no_baseline
