"""CLI: python -m clause_extractor [contracts_dir]"""
import os
import sys
from pathlib import Path

from . import AnthropicLLM, MockLLM, analyze_dir

DATA = Path(__file__).resolve().parent.parent / "data" / "contracts"
SKIP_FIELDS = {"we_are_uncapped", "we_are_payee"}


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM(fail_on={7})
    reports = analyze_dir(folder, llm)
    for r in sorted(reports, key=lambda r: -r.score):
        print(f"== {r.name} (we are {r.role})  risk score {r.score}")
        for c in r.clauses:
            if c.type == "other":
                continue
            fields = ", ".join(f"{k}={v}" for k, v in c.fields.items() if k not in SKIP_FIELDS and v not in (None, []))
            print(f"  §{c.number:<2} {c.type:<16} [{c.source:<5}] {fields}")
        for f in r.flags:
            print(f"  ! {f.severity.upper():<6} §{f.clause}: {f.message}")
        notes = []
        if r.fallbacks:
            notes.append(f"LLM output rejected for §{', §'.join(map(str, r.fallbacks))}; used rules")
        if r.disagreements:
            notes.append(f"LLM and rules disagree on §{', §'.join(map(str, r.disagreements))}: needs review")
        for n in notes:
            print(f"  note: {n}")
        print()


if __name__ == "__main__":
    main()
