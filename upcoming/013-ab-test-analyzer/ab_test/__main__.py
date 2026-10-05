"""CLI.
  python -m ab_test                          analyze data/experiments.json
  python -m ab_test plan 0.032 0.10          sample size for baseline 3.2%, +10% relative MDE
"""
import sys
from pathlib import Path

from . import analyze, load_experiments, sample_size_per_arm

DATA = Path(__file__).resolve().parent.parent / "data" / "experiments.json"


def plan(baseline: float, mde: float, daily_traffic: int = 20000) -> None:
    print(f"baseline {baseline:.2%}, MDE {mde:+.0%} relative, alpha 0.05 two-sided")
    for power in (0.8, 0.9):
        n = sample_size_per_arm(baseline, mde, power=power)
        days = -(-2 * n // daily_traffic)
        print(f"  power {power:.0%}: {n:,} per arm -> {days} days at {daily_traffic:,} visitors/day")


def report() -> None:
    for v in map(analyze, load_experiments(DATA)):
        e, t = v.experiment, v.test
        print(f"{e.name}: {v.decision}")
        print(f"  {e.hypothesis}")
        print(f"  control {t.p_control:.2%} (n={e.control[0]:,})  treatment {t.p_treatment:.2%} (n={e.treatment[0]:,})  "
              f"lift {t.rel_lift:+.1%}  diff 95% CI [{t.ci_low * 100:+.2f}, {t.ci_high * 100:+.2f}] pp")
        for r in v.reasons:
            print(f"  - {r}")
        print()


def main() -> None:
    if len(sys.argv) >= 4 and sys.argv[1] == "plan":
        plan(float(sys.argv[2]), float(sys.argv[3]))
    else:
        report()


if __name__ == "__main__":
    main()
