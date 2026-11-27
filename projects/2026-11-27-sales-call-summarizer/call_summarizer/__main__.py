"""CLI: python -m call_summarizer [transcript.txt ...]"""
import os
import sys
from pathlib import Path

from . import FIELDS, AnthropicLLM, MockLLM, extract, health, load

DATA = Path(__file__).resolve().parent.parent / "data" / "calls"
MARK = {"confirmed": "+", "partial": "~", "missing": "-", "unverified": "!"}


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]] or sorted(DATA.glob("*.txt"))
    if os.environ.get("ANTHROPIC_API_KEY"):
        llm = AnthropicLLM()
    else:
        # the mock invents one quote on the Cobalt call so the evidence check has something to catch
        llm = MockLLM(fabricate={"economic_buyer": "Cobalt Foods|Our finance director owns this budget and will sign."})
    results = sorted((extract(llm, load(p)) for p in paths), key=lambda a: -a.score)
    for a in results:
        c = a.call
        print(f"== {c.deal} ({c.stage}, ${c.amount:,.0f})  health {a.score}/100 {health(a.score).upper()}")
        for f in FIELDS:
            fld = a.fields[f]
            ev = f' "{fld.evidence[:78]}"' if fld.evidence else ""
            note = "  <- quote not found in transcript" if fld.status == "unverified" else ""
            print(f"  {MARK[fld.status]} {f:<18}{fld.status:<11}{ev}{note}".rstrip())
        if a.risks:
            print(f"  risks: {'; '.join(a.risks)}")
        if a.stage_gaps:
            print(f"  behind for {c.stage}: {', '.join(a.stage_gaps)}")
        for act in a.actions:
            print(f"  next: {act}")
        print()
    weighted = sum(a.call.amount * a.score / 100 for a in results)
    print(f"pipeline ${sum(a.call.amount for a in results):,.0f}, health-weighted ${weighted:,.0f}")


if __name__ == "__main__":
    main()
