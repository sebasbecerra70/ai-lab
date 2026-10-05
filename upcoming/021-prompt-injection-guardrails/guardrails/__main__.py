"""CLI: python -m guardrails  -- detector eval on labelled examples, then end-to-end scenarios with a gullible model."""
import json
import os
from pathlib import Path

from . import AnthropicLLM, GuardedAssistant, NaiveMock, score_injection

DATA = Path(__file__).resolve().parent.parent / "data"
SESSION = {"customer_email": "jane.doe@example.com", "order_ids": ["ORD-482913"]}


def evaluate() -> None:
    rows = [json.loads(x) for x in (DATA / "attacks.jsonl").read_text().splitlines() if x.strip()]
    tp = fp = fn = tn = 0
    misses = []
    for r in rows:
        caught = score_injection(r["text"], r["source"]).decision != "allow"
        attack = r["label"] == "attack"
        tp += caught and attack
        fp += caught and not attack
        fn += attack and not caught
        tn += not caught and not attack
        if caught != attack:
            misses.append(("missed" if attack else "false alarm", r["text"][:70]))
    print(f"injection detector on {len(rows)} labelled inputs: recall {tp / (tp + fn):.0%}, "
          f"false-positive rate {fp / (fp + tn):.0%} (tp={tp} fp={fp} fn={fn} tn={tn})")
    for kind, text in misses:
        print(f"  {kind}: {text}")


def scenarios() -> None:
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else NaiveMock()
    bot = GuardedAssistant(llm)
    print(f"\nscenarios (model: {type(llm).__name__}, which obeys any instruction it sees):")
    for sc in json.loads((DATA / "scenarios.json").read_text()):
        out = bot.handle(sc["message"], SESSION, sc["documents"])
        print(f"\n# {sc['name']}\n  user: {sc['message']}")
        for a in out.audit:
            print(f"  | {a}")
        print(f"  reply: {out.reply}")
        if out.executed:
            print(f"  executed: {out.executed}")
        if out.pending_approval:
            print(f"  awaiting approval: {out.pending_approval}")


if __name__ == "__main__":
    evaluate()
    scenarios()
