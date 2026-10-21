"""CLI: python -m postmortem [--timeline-only]"""
import json
import os
import sys
from pathlib import Path

from . import AnthropicLLM, MockLLM, build_facts, compute_metrics, draft_postmortem, lint, load_timeline

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    events = load_timeline(DATA)
    m = compute_metrics(events)
    raw = sum(len(e.sources) for e in events)
    print(f"timeline: {raw} raw events -> {len(events)} after collapsing repeats\n")
    for e in events:
        print("  " + e.render())
    print("\nmetrics: " + ", ".join(f"{k}={v}" for k, v in m.durations().items()))
    print(f"suspected trigger: {m.suspected_change}")
    if "--timeline-only" in sys.argv:
        return

    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM()
    roles = json.loads((DATA / "roles.json").read_text())
    facts = build_facts(events, m, "Checkout errors after PDU breaker trip in row 14", roles)
    draft = draft_postmortem(llm, facts)
    result = lint(draft, facts)
    print(f"\n----- draft ({type(llm).__name__}) -----\n{draft}\n-----")
    print(f"lint: {'PASS' if result.ok else 'FAIL'}  blame={result.blame_phrases} "
          f"ungrounded_times={result.unknown_times} missing_sections={result.missing_sections}")


if __name__ == "__main__":
    main()
