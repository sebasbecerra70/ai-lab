"""CLI: python -m outreach [prospect first name to print in full]"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import AnthropicClient, MockLLM, draft_email, failures


def main() -> None:
    data = Path(__file__).resolve().parent.parent / "data"
    product = json.loads((data / "product.json").read_text())
    prospects = json.loads((data / "prospects.json").read_text())
    llm = AnthropicClient() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM()
    show = sys.argv[1] if len(sys.argv) > 1 else prospects[0]["first_name"]
    print(f"Drafting {len(prospects)} emails with {type(llm).__name__}; each draft must pass 9 checks\n")

    drafts = [draft_email(llm, p, product) for p in prospects]
    names = [c.name for c in drafts[0].attempts[0]]
    print(f"{'prospect':<36}{'attempts':>9}  first-draft failures -> final")
    for d in drafts:
        p = d.prospect
        first = "; ".join(f"{c.name} ({c.detail})" if c.detail else c.name for c in failures(d.attempts[0])) or "none"
        final = "PASS" if d.passed else "FAIL: " + ", ".join(c.name for c in failures(d.attempts[-1]))
        print(f"{p['first_name'] + ' @ ' + p['company']:<36}{len(d.attempts):>9}  {first} -> {final}")

    n = len(drafts)
    print(f"\nfirst-draft pass rate {sum(d.first_pass for d in drafts)}/{n}; "
          f"after revise loop {sum(d.passed for d in drafts)}/{n}")
    per_check = {name: sum(not d.attempts[0][i].passed for d in drafts) for i, name in enumerate(names)}
    print("first-draft failures by check: " + ", ".join(f"{k} {v}" for k, v in per_check.items() if v))

    d = next((x for x in drafts if x.prospect["first_name"].lower() == show.lower()), drafts[0])
    print(f"\n--- final email to {d.prospect['first_name']} {d.prospect['last_name']} ---")
    print(f"Subject: {d.email['subject']}\n\n{d.email['body']}")


if __name__ == "__main__":
    main()
