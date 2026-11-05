"""CLI: python -m energy_scheduler [--cap-kw 900] [--carbon-price 100]"""
import argparse
from pathlib import Path

from . import evaluate, gantt, load_grid, load_jobs, schedule_asap, schedule_optimized, tradeoff_curve

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap-kw", type=float, default=900, help="facility power headroom for batch")
    ap.add_argument("--carbon-price", type=float, default=100, help="shadow price, $ per t CO2")
    args = ap.parse_args()
    jobs, grid = load_jobs(DATA / "jobs.csv"), load_grid(DATA / "grid_48h.csv")

    base = evaluate(schedule_asap(jobs, grid, args.cap_kw), jobs, grid)
    opt_sched = schedule_optimized(jobs, grid, args.cap_kw, args.carbon_price)
    opt = evaluate(opt_sched, jobs, grid)
    print(f"{len(jobs)} jobs, 48h horizon, cap {args.cap_kw:.0f} kW, carbon price ${args.carbon_price:.0f}/t\n")
    print(f"{'plan':<10}{'cost $':>9}{'CO2 kg':>9}{'peak kW':>9}  deadlines")
    for name, m in (("asap", base), ("optimized", opt)):
        print(f"{name:<10}{m.cost_usd:>9.0f}{m.carbon_kg:>9.0f}{m.peak_kw:>9.0f}  {'met' if m.deadlines_met else 'MISSED'}")
    print(f"savings: {1 - opt.cost_usd / base.cost_usd:.1%} cost, {1 - opt.carbon_kg / base.carbon_kg:.1%} carbon\n")
    print("hour              |" + "".join(str(h % 10) for h in range(len(grid))) + "|")
    print(gantt(opt_sched, jobs, len(grid)))
    print("\ncarbon price $/t -> cost $, CO2 kg")
    for cp, m in tradeoff_curve(jobs, grid, args.cap_kw):
        print(f"  {cp:>4} -> {m.cost_usd:7.0f}, {m.carbon_kg:7.0f}")


if __name__ == "__main__":
    main()
