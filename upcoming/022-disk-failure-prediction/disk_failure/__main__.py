"""CLI: python -m disk_failure [unplanned_failure_cost] [proactive_swap_cost]"""
import sys
from pathlib import Path

from . import (FEATURES, Costs, LogisticRegression, Scaler, at_threshold, average_precision, best_threshold, features, load,
               roc_auc, rule_baseline, stratified_split)

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    costs = Costs(*(float(a) for a in sys.argv[1:3])) if len(sys.argv) > 2 else Costs()
    rows = load(DATA / "fleet_history.csv")
    train, test = stratified_split(rows)
    scaler = Scaler.fit([features(r) for r in train])
    X = lambda rs: [scaler.transform(features(r)) for r in rs]  # noqa: E731
    y_train, y_test = [int(r["failed_30d"]) for r in train], [int(r["failed_30d"]) for r in test]
    model = LogisticRegression(pos_weight=10).fit(X(train), y_train)
    p = model.predict_proba(X(test))

    print(f"fleet history: {len(rows)} drives, {sum(int(r['failed_30d']) for r in rows)} failed within 30 days "
          f"({sum(int(r['failed_30d']) for r in rows) / len(rows):.1%})")
    print(f"test set: {len(test)} drives, {sum(y_test)} failures   ROC AUC {roc_auc(p, y_test):.3f}   "
          f"avg precision {average_precision(p, y_test):.3f} (random = {sum(y_test) / len(y_test):.3f})\n")
    print("coefficients (per 1 sd):")
    for name, w in sorted(zip(FEATURES, model.w), key=lambda t: -abs(t[1])):
        print(f"  {name:<22}{w:+.2f}")

    print(f"\n{'threshold':>10}{'flagged':>9}{'precision':>11}{'recall':>8}{'cost':>11}")
    for t in (0.2, 0.4, 0.6, 0.8):
        r = at_threshold(p, y_test, t)
        print(f"{t:>10.2f}{r.flagged:>9}{r.precision:>11.0%}{r.recall:>8.0%}{costs.total(r):>11,.0f}")
    # Pick the threshold on training data, then report it on the held-out drives (no peeking at test labels).
    best = at_threshold(p, y_test, best_threshold(model.predict_proba(X(train)), y_train, costs).threshold)
    rule = at_threshold(rule_baseline(test), y_test, 0.5)
    nothing = at_threshold([0.0] * len(test), y_test, 0.5)
    print(f"\ncosts: unplanned failure ${costs.unplanned_failure:,.0f}, proactive swap ${costs.proactive_swap:,.0f}")
    print(f"  do nothing (run to failure)       ${costs.total(nothing):>9,.0f}")
    print(f"  rule: any realloc/pending sector  ${costs.total(rule):>9,.0f}   flags {rule.flagged}, recall {rule.recall:.0%}, precision {rule.precision:.0%}")
    print(f"  model @ cost-optimal t={best.threshold:.2f}    ${costs.total(best):>9,.0f}   flags {best.flagged}, recall {best.recall:.0%}, precision {best.precision:.0%}")

    today = load(DATA / "fleet_today.csv")
    scores = model.predict_proba(X(today))
    ranked = sorted(zip(scores, today), key=lambda t: -t[0])
    flagged = [(s, r) for s, r in ranked if s >= best.threshold]
    print(f"\ntoday's fleet: {len(flagged)} of {len(today)} drives to swap proactively; top 5:")
    for s, r in flagged[:5]:
        print(f"  {r['serial']} {r['model']:<7} p={s:.2f}  realloc={r['reallocated_sectors']:>3} pending={r['pending_sectors']:>2} "
              f"uncorr={r['uncorrectable_errors']:>2} seek={r['seek_error_rate']}")


if __name__ == "__main__":
    main()
