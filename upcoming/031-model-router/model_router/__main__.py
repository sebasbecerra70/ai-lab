"""CLI: python -m model_router ["your prompt"]"""
import os
import sys
from pathlib import Path

from . import AnthropicLLM, DifficultyClassifier, MockLLM, Router, frontier, load_jsonl
from .router import accuracy

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    texts, labels = load_jsonl(DATA / "prompts.jsonl")
    clf = DifficultyClassifier().fit(texts, labels)
    ho_texts, ho_labels = load_jsonl(DATA / "holdout.jsonl")
    print(f"classifier: train acc {accuracy(clf, texts, labels):.0%}, "
          f"holdout acc {accuracy(clf, ho_texts, ho_labels):.0%}; top features {clf.top_features()}")

    print("\npolicy           $/day @100k   quality   %large")
    for r in frontier(clf, ho_texts, ho_labels):
        print(f"{r.policy:<16} {r.cost_usd:>11,.0f}   {r.expected_quality:>6.1%}   {r.pct_large:>5.0%}")

    if os.environ.get("ANTHROPIC_API_KEY"):
        clients = {"small": AnthropicLLM("claude-haiku-4-5"), "large": AnthropicLLM()}
    else:
        clients = {"small": MockLLM("small"), "large": MockLLM("large")}
    prompts = sys.argv[1:] or ["Convert 12 pounds to kilograms.",
                               "Design a rollout plan for a new pricing tier and explain the trade-offs."]
    print()
    for p in prompts:
        decision, answer = Router(clf).run(p, clients)
        print(f"p_hard={decision.p_hard:.2f} -> {decision.tier.name}: {answer}")


if __name__ == "__main__":
    main()
