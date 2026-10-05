"""CLI: python -m account_agent ["Company Name"]"""
import json
import os
import sys
from pathlib import Path

from . import AnthropicLLM, DocStore, MockLLM, ResearchAgent, check_citations, score_fit

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    account = " ".join(sys.argv[1:]) or "Harbor Retail"
    store = DocStore.from_dir(DATA)
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM()
    result = ResearchAgent(llm, store).run(account)

    print(f"agent: {type(llm).__name__}, target: {account}")
    for i, s in enumerate(result.steps, 1):
        obs = json.dumps(s.observation)
        print(f"  step {i}: {s.tool}({', '.join(f'{k}={v!r}' for k, v in s.args.items())}) -> {obs[:70]}{'...' if len(obs) > 70 else ''}")
    print(f"\n{result.brief}\n")
    check = check_citations(result.brief, result.seen_refs)
    print(f"grounding: {check['cited']} sources cited, unseen={check['unseen']}, uncited bullets={len(check['uncited_bullets'])}")

    print("\nICP fit across all profiles:")
    for doc, title in sorted(store.titles.items()):
        if doc != "our_product":
            fit = score_fit(store, doc)
            print(f"  {title:<16} {fit['score']}/{fit['max']}  " + ", ".join(r["criterion"] for r in fit["reasons"] if r["met"]))


if __name__ == "__main__":
    main()
