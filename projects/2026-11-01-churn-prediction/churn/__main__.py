"""CLI: python -m churn [top_n_at_risk]"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

from . import HORIZON, ChurnModel, auc, label, load_accounts, months_observed, retention_triangle, split, blended_curve


def main() -> None:
    data = Path(__file__).resolve().parent.parent / "data"
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    accounts = load_accounts(data / "accounts.csv")
    latest = max(a.cohort for a in accounts)

    tri = retention_triangle(accounts)
    print(f"Cohort retention ({len(accounts)} accounts; % still active after month N; C01 = oldest signup month)")
    cols = range(1, latest + 1)
    print("cohort  size " + "".join(f"{f'M{m}':>5}" for m in cols))
    for c, row in tri.items():
        size = sum(a.cohort == c for a in accounts)
        print(f"C{c:02d}   {size:>5} " + "".join(f"{v:>5.0%}" for v in row))
    curve = blended_curve(accounts)
    print("blended      " + "".join(f"{v:>5.0%}" for v in curve) + "   (Kaplan-Meier)")

    mature = [a for a in accounts if months_observed(a, latest) >= HORIZON]
    train, test = split(mature)
    model = ChurnModel().fit(train)
    y = [label(a) for a in test]
    p = [model.predict(a) for a in test]
    base = [-a.active_days_first30 for a in test]
    print(f"\nEarly-warning model: P(cancel within {HORIZON} months | first 30 days), "
          f"trained on {len(train)} accounts, tested on {len(test)} (churn rate {sum(y) / len(y):.0%})")
    print(f"  holdout AUC {auc(y, p):.2f}  vs  {auc(y, base):.2f} for 'fewest active days' alone")
    print("  drivers (odds ratio per +1 std dev; <1 protects, >1 raises churn):")
    for name, ratio in model.drivers()[:5]:
        print(f"    {name:<28}{ratio:>5.2f}")

    young = [a for a in accounts if months_observed(a, latest) < HORIZON and a.churn_month is None]
    lift = [model.predict(a) - model.predict(replace(a, onboarding_completed=1))
            for a in young if not a.onboarding_completed]
    print(f"\nAt-risk: {len(young)} active accounts still inside their first {HORIZON} months; top {top_n}")
    ranked = sorted(young, key=lambda a: -model.predict(a))[:top_n]
    for a in ranked:
        print(f"  {a.account_id} C{a.cohort:02d} {a.plan:<9}{a.seats:>4} seats {model.predict(a):>5.0%}  "
              + "; ".join(model.reasons(a)))
    print(f"\nWhat-if: {len(lift)} young accounts never finished onboarding. If they had, modelled 6-month churn")
    print(f"falls {sum(lift) / len(lift) * 100:.1f} pts each (~{sum(lift):.0f} accounts kept). Correlational: confirm with an "
          "onboarding-outreach A/B test.")


if __name__ == "__main__":
    main()
