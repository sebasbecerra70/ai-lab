"""CLI: python -m intel_digest [prev_dir curr_dir]"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

from . import AnthropicLLM, MockLLM, diff_all, write_digest

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    prev, curr = (Path(p) for p in sys.argv[1:3]) if len(sys.argv) > 2 else (DATA / "prev", DATA / "curr")
    us = json.loads((DATA / "us.json").read_text())
    changes = diff_all(prev, curr, watch=set(us["differentiators"]))
    sev = Counter(c.severity for c in changes)
    print(f"{len(changes)} changes across {len({c.competitor for c in changes})} competitors: "
          f"{sev['high']} high, {sev['medium']} medium, {sev['low']} low\n")
    for c in changes:
        print(f"  {c.id:<4}{c.severity:<7}{c.competitor:<11}{c.kind:<16}{c.detail}")
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM()
    text, a = write_digest(llm, changes, us)
    print("\n=== digest ===")
    print(text)
    print("\ncitation audit: " + ("passed" if a.ok else f"unknown ids {a.unknown}, uncited high-severity {a.uncited_high}"))


if __name__ == "__main__":
    main()
