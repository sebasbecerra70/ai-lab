"""Graders: exact, contains, regex, json_keys and LLM-as-judge. Each returns a Grade with a reason."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .llm import LLMClient


@dataclass
class Grade:
    passed: bool
    reason: str


def _norm(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text).strip().lower()


def grade_exact(output: str, expected: str, normalize: bool = False) -> Grade:
    a, b = (_norm(output), _norm(expected)) if normalize else (output.strip(), expected)
    return Grade(a == b, "exact match" if a == b else f"expected {expected!r}, got {output.strip()!r}")


def grade_contains(output: str, all: list[str] | None = None, any: list[str] | None = None,  # noqa: A002
                   none: list[str] | None = None) -> Grade:
    low = output.lower()
    missing = [s for s in (all or []) if s.lower() not in low]
    if missing:
        return Grade(False, f"missing {missing}")
    if any and not [s for s in any if s.lower() in low]:
        return Grade(False, f"none of {any} present")
    banned = [s for s in (none or []) if s.lower() in low]
    if banned:
        return Grade(False, f"contains banned {banned}")
    return Grade(True, "all required phrases present")


def grade_regex(output: str, pattern: str, must_not: str | None = None) -> Grade:
    if must_not and re.search(must_not, output.strip(), re.MULTILINE):
        return Grade(False, f"matched forbidden /{must_not}/")
    ok = re.search(pattern, output.strip(), re.MULTILINE) is not None
    return Grade(ok, f"matched /{pattern}/" if ok else f"no match for /{pattern}/")


def grade_json_keys(output: str, keys: list[str]) -> Grade:
    try:
        obj = json.loads(output)
    except json.JSONDecodeError as exc:
        return Grade(False, f"invalid JSON: {exc.msg}")
    if not isinstance(obj, dict):
        return Grade(False, "JSON is not an object")
    missing = [k for k in keys if k not in obj]
    return Grade(not missing, f"missing keys {missing}" if missing else "valid JSON with required keys")


JUDGE_SYSTEM = (
    "You are a strict grader. For each numbered criterion decide if the RESPONSE satisfies it. "
    'Reply with JSON only: {"verdicts": [{"criterion": 1, "pass": true, "reason": "..."}]}'
)


def judge_prompt(question: str, output: str, rubric: list[str]) -> str:
    crit = "\n".join(f"{i}. {c}" for i, c in enumerate(rubric, 1))
    return f"QUESTION:\n{question}\n\nRESPONSE:\n{output}\n\nCRITERIA:\n{crit}"


def grade_llm_judge(output: str, rubric: list[str], judge: LLMClient, question: str = "") -> Grade:
    """Every criterion must pass. Per-criterion verdicts beat one holistic score: they are more
    consistent run to run and they tell you *what* to fix."""
    raw = judge.complete(JUDGE_SYSTEM, judge_prompt(question, output, rubric))
    try:
        verdicts = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])["verdicts"]
    except (ValueError, KeyError):
        return Grade(False, "judge returned unparseable output")
    if len(verdicts) != len(rubric):
        return Grade(False, f"judge returned {len(verdicts)} verdicts for {len(rubric)} criteria")
    failed = [f"#{v['criterion']} {v.get('reason', '')}".strip() for v in verdicts if not v.get("pass")]
    return Grade(not failed, "all criteria met" if not failed else "; ".join(failed))


def grade(spec: dict, output: str, judge: LLMClient | None = None, question: str = "") -> Grade:
    kind = spec["type"]
    args = {k: v for k, v in spec.items() if k != "type"}
    if kind == "exact":
        return grade_exact(output, **args)
    if kind == "contains":
        return grade_contains(output, **args)
    if kind == "regex":
        return grade_regex(output, **args)
    if kind == "json_keys":
        return grade_json_keys(output, **args)
    if kind == "llm_judge":
        if judge is None:
            raise ValueError("llm_judge grader needs a judge client")
        return grade_llm_judge(output, args["rubric"], judge, question)
    raise ValueError(f"unknown grader type {kind!r}")
