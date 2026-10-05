"""CLI: python -m llm_eval [--live] [--save-baseline]

Default: grade recorded outputs in data/model_outputs.json with the offline keyword judge.
--live: generate outputs and judge with Claude (needs ANTHROPIC_API_KEY).
Exit code is 1 when the gate fails, so this can run in CI.
"""
import json
import os
import sys
from pathlib import Path

from . import AnthropicLLM, KeywordJudge, ReplayLLM, load_cases, render, run


def main() -> int:
    data = Path(__file__).resolve().parent.parent / "data"
    cases = load_cases(data / "cases.json")
    if "--live" in sys.argv and os.environ.get("ANTHROPIC_API_KEY"):
        sut, judge = AnthropicLLM(), AnthropicLLM()
    else:
        recorded = json.loads((data / "model_outputs.json").read_text())
        sut, judge = ReplayLLM({c.prompt: recorded.get(c.id, "") for c in cases}), KeywordJudge()
    report = run(cases, sut, judge)
    baseline_path = data / "baseline.json"
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
    text, ok = render(report, baseline)
    print(text)
    if "--save-baseline" in sys.argv:
        baseline_path.write_text(json.dumps(report.to_json(), indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
