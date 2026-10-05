"""CLI: python -m llm_judge  -- runs pairwise (with swap) and rubric judging on the sample sets."""
import json
import os
from pathlib import Path

from . import AnthropicLLM, MockJudge, judge_pair, judge_rubric, pairwise_report, spearman

DATA = Path(__file__).resolve().parent.parent / "data"


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / name).read_text().splitlines() if line.strip()]


def main() -> None:
    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockJudge()
    print(f"judge: {type(llm).__name__}\n")

    pairs = load("pairs.jsonl")
    verdicts = [judge_pair(llm, p["question"], p["a"], p["b"], p["reference"]) for p in pairs]
    print("pairwise (A shown first, then B shown first):")
    for p, v in zip(pairs, verdicts):
        flag = "" if v.consistent else "  <- flipped with order"
        print(f"  {p['id']}  fwd={v.forward:<3} bwd={v.backward:<3} final={v.winner:<3} human={p['human']:<3}{flag}")
    r = pairwise_report(verdicts, [p["human"] for p in pairs])
    print(f"\n  flip rate on swap            {r.flip_rate:.0%}")
    print(f"  first-position win rate      {r.first_position_win_rate:.0%}  (50% = no position bias)")
    print(f"  agreement, single pass       {r.single_pass_agreement:.0%}")
    print(f"  agreement, swap-consistent   {r.swapped_agreement:.0%}  (kappa {r.swapped_kappa:.2f})")

    items = load("rubric_set.jsonl")
    scores = [judge_rubric(llm, it["question"], it["answer"], it["reference"]) for it in items]
    print("\nrubric (1-5):")
    for it, s in zip(items, scores):
        detail = " ".join(f"{k[:4]}={v}" for k, v in s.scores.items())
        print(f"  {it['id']}  {detail}  overall={s.overall:.2f}  human={it['human']}")
    rho = spearman([s.overall for s in scores], [it["human"] for it in items])
    print(f"\n  Spearman rho vs human overall: {rho:.2f}")


if __name__ == "__main__":
    main()
