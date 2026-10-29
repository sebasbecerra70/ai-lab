"""CLI: python -m delay_risk [rounds]"""
from __future__ import annotations

import sys
from pathlib import Path
from statistics import median

from . import (StumpEnsemble, auc, baseline_rates, brier, dataset, lane_carrier_matrix, load_rows, precision_at,
               score_plan, time_split)


def main() -> None:
    data = Path(__file__).resolve().parent.parent / "data"
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    rows = load_rows(data / "shipments.csv")
    train, test = time_split(rows)
    Xtr, ytr = dataset(train)
    Xte, yte = dataset(test)
    model = StumpEnsemble(rounds).fit(Xtr, ytr)
    p = [model.predict_proba(x) for x in Xte]
    carrier_rate = baseline_rates(train, "carrier")
    p_base = [carrier_rate[r["carrier"]] for r in test]
    k = len(test) // 5
    print(f"Trained {len(model.stumps)} stumps on {len(train)} shipments (weeks 0-{train[-1]['week']}), "
          f"tested on the next {len(test)}; delay rate {sum(yte) / len(yte):.0%}")
    print(f"{'model':<26}{'AUC':>6}{'Brier':>8}{f'prec@top{k}':>13}")
    print(f"{'carrier on-time history':<26}{auc(yte, p_base):>6.2f}{brier(yte, p_base):>8.3f}{precision_at(yte, p_base, k):>13.0%}")
    print(f"{'stump ensemble':<26}{auc(yte, p):>6.2f}{brier(yte, p):>8.3f}{precision_at(yte, p, k):>13.0%}")
    print("Top drivers: " + ", ".join(f"{f} {w:.0%}" for f, w in list(model.importance().items())[:5]))

    model = StumpEnsemble(rounds).fit(*dataset(rows))  # refit on all history before scoring the plan
    matrix = lane_carrier_matrix(model, rows)
    carriers = sorted(next(iter(matrix.values())))
    print("\nLane x carrier risk, typical FTL load (Tue, off-peak, median weather)")
    print(f"{'lane':<9}" + "".join(f"{c:>11}" for c in carriers) + "   best")
    for lane, by_c in matrix.items():
        best = min(by_c, key=by_c.get)
        print(f"{lane:<9}" + "".join(f"{by_c[c]:>11.0%}" for c in carriers) + f"   {best}")

    plan = load_rows(data / "upcoming.csv")
    otp = {c: median(float(r["carrier_otp_90d"]) for r in rows if r["carrier"] == c) for c in carriers}
    print(f"\nNext week's plan: {len(plan)} shipments")
    for r in score_plan(model, plan, carriers, otp):
        swap = f"  -> {r.swap[0]} {r.swap[1]:.0%}" if r.swap else ""
        why = "; ".join(r.reasons) if r.tier != "ok" else ""
        print(f"  {r.shipment_id} {r.lane:<8} {r.carrier:<10}{r.risk:>5.0%} {r.tier:<6}{why}{swap}".rstrip())


if __name__ == "__main__":
    main()
