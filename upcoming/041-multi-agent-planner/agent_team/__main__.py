"""CLI: python -m agent_team [servers]"""
import json
import os
import sys
from pathlib import Path

from . import AnthropicLLM, MockLLM, solve

FACTS = json.loads((Path(__file__).resolve().parent.parent / "data" / "facts.json").read_text())


def main() -> None:
    servers = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    task = (f"We must add {servers} 1U servers to our data hall. How many racks do we need, can the facility "
            "power it, what does it cost, and what do you recommend?")
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM()
    out = solve(task, {"servers": servers}, FACTS, llm)
    print(f"TASK: {task}\n")
    print("SCRATCHPAD")
    print(out.pad.render())
    print(f"\n{'APPROVED' if out.approved else 'NOT APPROVED'} after {out.rounds} round(s); "
          f"LLM calls {out.usage.calls}, ~{out.usage.approx_tokens} tokens")
    print(f"\nANSWER: {out.answer}")


if __name__ == "__main__":
    main()
