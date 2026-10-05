"""CLI: python -m lead_scoring   train on 75% of leads, evaluate on 25%, explain the top leads."""
from pathlib import Path

from . import LeadScorer, auc, lift_at, load_leads, train_test_split


def _fmt(reasons):
    return ", ".join(f"{name} {c:+.2f}" for name, c in reasons)


def main() -> None:
    rows = load_leads(Path(__file__).resolve().parent.parent / "data" / "leads.csv")
    train, test = train_test_split(rows)
    scorer = LeadScorer().fit(train)
    y = [int(r["converted"]) for r in test]
    scores = [scorer.score(r).probability for r in test]
    print(f"leads: {len(train)} train / {len(test)} test, base conversion {sum(y) / len(y):.1%}")
    print(f"test AUC {auc(y, scores):.3f}   lift@top20% {lift_at(y, scores, 0.2):.2f}x")
    print("\ncoefficients (standardized, log-odds per 1 sd):")
    for name, w in scorer.coefficients()[:8]:
        print(f"  {name:<26}{w:+.2f}")
    print("\ntop 5 open leads to call today:")
    ranked = sorted((scorer.score(r) for r in test), key=lambda s: -s.probability)[:5]
    for s in ranked:
        print(f"  {s.lead_id} tier {s.tier} p={s.probability:.2f}  because {_fmt(s.reasons)}")
    tiers = {}
    for r, p in zip(test, scores):
        t = scorer.score(r).tier
        hits, n = tiers.get(t, (0, 0))
        tiers[t] = (hits + int(r["converted"]), n + 1)
    print("\nconversion by tier: " + "  ".join(f"{t}: {h}/{n} ({h / n:.0%})" for t, (h, n) in sorted(tiers.items())))


if __name__ == "__main__":
    main()
