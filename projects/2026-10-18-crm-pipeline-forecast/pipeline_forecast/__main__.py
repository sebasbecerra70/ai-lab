"""CLI: python -m pipeline_forecast [days_left_in_quarter] [target]"""
import sys
from collections import defaultdict
from pathlib import Path

from . import STAGES, at_risk_commits, fit_stage_stats, forecast, load_history, load_pipeline

DATA = Path(__file__).resolve().parent.parent / "data"


def k(x: float) -> str:
    return f"${x / 1000:,.0f}k"


def main() -> None:
    days_left = int(sys.argv[1]) if len(sys.argv) > 1 else 45
    target = float(sys.argv[2]) if len(sys.argv) > 2 else 900_000
    stats = fit_stage_stats(load_history(DATA / "history.csv"))
    pipeline = load_pipeline(DATA / "pipeline.csv")

    print("learned from closed deals:")
    print(f"  {'stage':<12}{'win rate':>9}{'fresh':>8}{'stale':>8}{'stale after':>13}")
    for s in STAGES:
        st = stats[s]
        print(f"  {s:<12}{st.win_rate:>9.0%}{st.win_rate_fresh:>8.0%}{st.win_rate_stale:>8.0%}{st.stale_after_days:>10.0f} d")

    fc = forecast(pipeline, stats, days_left, target)
    print(f"\nopen pipeline: {len(pipeline)} deals, {k(sum(d.amount for d in pipeline))}; {days_left} days left; target {k(target)}")
    by_stage = defaultdict(lambda: [0, 0.0, 0.0])
    for f in fc.deals:
        row = by_stage[f.deal.stage]
        row[0] += 1
        row[1] += f.deal.amount
        row[2] += f.expected
    for s in STAGES:
        n, amt, exp = by_stage[s]
        print(f"  {s:<12}{n:>3} deals {k(amt):>8} -> {k(exp):>6} expected")

    print("\nforecast:")
    print(f"  rep commit              {k(fc.rep_commit):>8}")
    print(f"  naive stage-weighted    {k(fc.naive_weighted):>8}  (ignores aging and timing)")
    print(f"  aged + timed weighted   {k(fc.weighted):>8}")
    print(f"  Monte Carlo P10/P50/P90 {k(fc.p10)} / {k(fc.p50)} / {k(fc.p90)}")
    print(f"  {'P(hit ' + k(target) + ')':<24}{fc.p_hit_target:>8.0%}")

    print("\ncommits to pressure-test:")
    for f in at_risk_commits(fc)[:5]:
        why = f"stale {f.deal.days_in_stage}d in {f.deal.stage}" if f.stale else f"{f.p_in_quarter:.0%} chance of closing in time"
        print(f"  {f.deal.deal_id} {f.deal.account:<20} {k(f.deal.amount):>6} {f.deal.owner:<7} p_close={f.p_close:.0%}  ({why})")


if __name__ == "__main__":
    main()
