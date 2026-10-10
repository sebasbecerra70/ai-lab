"""Run cases through a model, grade them, and compare against a saved baseline."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .graders import Grade, grade
from .llm import LLMClient

SUT_SYSTEM = "You are a customer-support assistant for an industrial equipment distributor. Be accurate and brief."


@dataclass(frozen=True)
class Case:
    id: str
    prompt: str
    grader: dict
    tags: tuple[str, ...] = ()


@dataclass
class CaseResult:
    case: Case
    output: str
    grade: Grade


@dataclass
class Report:
    results: list[CaseResult]

    @property
    def pass_rate(self) -> float:
        return sum(r.grade.passed for r in self.results) / len(self.results) if self.results else 0.0

    def by(self, key) -> dict[str, tuple[int, int]]:
        acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in self.results:
            for k in key(r):
                acc[k][0] += r.grade.passed
                acc[k][1] += 1
        return {k: (v[0], v[1]) for k, v in sorted(acc.items())}

    def by_tag(self) -> dict[str, tuple[int, int]]:
        return self.by(lambda r: r.case.tags)

    def by_grader(self) -> dict[str, tuple[int, int]]:
        return self.by(lambda r: [r.case.grader["type"]])

    def diff(self, baseline: dict) -> tuple[list[str], list[str]]:
        """(regressions, fixes) relative to a baseline {case_id: passed}."""
        regressions = [r.case.id for r in self.results if baseline.get(r.case.id) is True and not r.grade.passed]
        fixes = [r.case.id for r in self.results if baseline.get(r.case.id) is False and r.grade.passed]
        return regressions, fixes

    def to_json(self) -> dict:
        return {"pass_rate": round(self.pass_rate, 4), "results": {r.case.id: r.grade.passed for r in self.results}}


def load_cases(path: str | Path) -> list[Case]:
    raw = json.loads(Path(path).read_text())
    ids = [c["id"] for c in raw]
    if len(ids) != len(set(ids)):
        raise ValueError("case ids must be unique")
    return [Case(c["id"], c["prompt"], c["grader"], tuple(c.get("tags", []))) for c in raw]


def run(cases: list[Case], sut: LLMClient, judge: LLMClient | None = None) -> Report:
    results = []
    for case in cases:
        output = sut.complete(SUT_SYSTEM, case.prompt)
        try:
            g = grade(case.grader, output, judge, case.prompt)
        except Exception as exc:  # a broken grader is a failed case, not a crashed run
            g = Grade(False, f"grader error: {exc}")
        results.append(CaseResult(case, output, g))
    return Report(results)


def render(report: Report, baseline: dict | None = None, gate: float = 0.8) -> tuple[str, bool]:
    lines = [f"pass rate: {report.pass_rate:.0%} ({sum(r.grade.passed for r in report.results)}/{len(report.results)})"]
    lines.append("by tag:    " + "  ".join(f"{k} {p}/{n}" for k, (p, n) in report.by_tag().items()))
    lines.append("by grader: " + "  ".join(f"{k} {p}/{n}" for k, (p, n) in report.by_grader().items()))
    failures = [r for r in report.results if not r.grade.passed]
    if failures:
        lines.append("failures:")
        lines += [f"  - {r.case.id} [{r.case.grader['type']}]: {r.grade.reason}" for r in failures]
    ok = report.pass_rate >= gate
    if baseline is not None:
        regressions, fixes = report.diff(baseline.get("results", {}))
        lines.append(f"vs baseline {baseline.get('pass_rate', 0):.0%}: regressions {regressions or 'none'}, "
                     f"fixes {fixes or 'none'}")
        ok = ok and not regressions
    lines.append(f"gate (>= {gate:.0%}, no regressions): {'PASS' if ok else 'FAIL'}")
    return "\n".join(lines), ok
