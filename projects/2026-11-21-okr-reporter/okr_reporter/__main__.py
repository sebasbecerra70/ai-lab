"""CLI: python -m okr_reporter [okrs.json metrics.csv]"""
import os
import sys
from pathlib import Path

from . import AnthropicLLM, MockLLM, fmt, score, write_update

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    okr_path, metrics_path = (Path(p) for p in sys.argv[1:3]) if len(sys.argv) > 2 else (DATA / "okrs.json", DATA / "metrics.csv")
    cfg, objectives, week = score(okr_path, metrics_path)
    total = cfg["weeks_in_quarter"]
    print(f"{cfg['quarter']} OKRs, week {week} of {total} ({week / total:.0%} of the quarter elapsed)\n")
    print(f"{'KR':<7}{'key result':<38}{'now':>14}{'target':>14}{'done':>6}{'pace':>6}{'forecast':>15}  status")
    for o in objectives:
        print(f"{o.id}  {o.title}  (score {o.score:.0%}, projected {o.projected:.0%})")
        for k in o.krs:
            print(f"{k.id:<7}{k.title[:36]:<38}{fmt(k, k.current):>14}{fmt(k, k.target):>14}{k.progress:>6.0%}"
                  f"{k.expected:>6.0%}{fmt(k, k.forecast):>15}  {k.status}")
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM()
    text, chk = write_update(llm, objectives, week, total)
    print("\n--- status update draft ---")
    print(text)
    print("---")
    print("fact check: " + ("passed" if chk.ok else f"unknown numbers {chk.unknown_numbers}, missing {chk.missing_krs}"))


if __name__ == "__main__":
    main()
