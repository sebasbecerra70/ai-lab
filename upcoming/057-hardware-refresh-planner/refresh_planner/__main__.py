"""CLI: python -m refresh_planner [policy]"""
import sys
from pathlib import Path

from . import POLICIES, cohort_opex, load_assumptions, load_fleet, run, server_opex

DATA = Path(__file__).resolve().parent.parent / "data"


def k(x: float) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x) / 1e6:.2f}M" if abs(x) >= 1e6 else f"{sign}${abs(x) / 1e3:.0f}k"


def main() -> None:
    fleet, a = load_fleet(DATA / "fleet.csv"), load_assumptions(DATA / "assumptions.json")
    show = sys.argv[1] if len(sys.argv) > 1 else "TCO-optimized"
    print(f"Fleet: {sum(c.servers for c in fleet)} servers in {len(fleet)} cohorts, "
          f"run cost {k(sum(cohort_opex(c, a) for c in fleet))}/yr")
    old, new = server_opex(7, 420, 5, a), server_opex(0, 650, 5, a)
    print("Per-server run cost, 7-year-old gen3 vs new gen6: "
          + ", ".join(f"{key} ${old[key]:.0f}/${new[key]:.0f}" for key in old))

    results = {p: run(fleet, a, p) for p in POLICIES}
    r = results[show]
    print(f"\n{show} plan")
    for y in r.years:
        flag = "  OVER BUDGET" if y.spent > y.budget + 1 else ""
        print(f"Year {y.year}: spend {k(y.spent)} of {k(y.budget)}{flag}")
        merged: dict[tuple, list] = {}
        for x in y.actions:
            m = merged.setdefault((x.cohort, x.platform, x.reason), [0, 0, 0.0, 0.0])
            m[0] += x.servers; m[1] += x.new_servers; m[2] += x.capex; m[3] += x.npv
        for (name, plat, reason), (s, n, capex, npv) in merged.items():
            print(f"   {name:<12} {s:>4} -> {n:>3} {plat}  capex {k(capex):>7}  NPV {k(npv):>7}  ({reason})")
        if y.deferred:
            print(f"   waiting for next platform: {', '.join(y.deferred)}")

    print(f"\nPolicy comparison over {a.horizon_years} years (capacity held constant)")
    print(f"{'policy':<15}{'PV cost':>9}{'PV cash':>9}{'capex':>8}{'exit run-rate':>15}{'servers':>9}{'past warranty':>15}")
    for p, res in results.items():
        capex = sum(y.spent for y in res.years)
        past = sum(c.servers for c in res.exit_fleet if c.age > c.warranty_years)
        print(f"{p:<15}{k(res.pv_cost):>9}{k(res.pv_cash):>9}{k(capex):>8}{k(res.exit_opex) + '/yr':>15}"
              f"{sum(c.servers for c in res.exit_fleet):>9}{past:>15}")
    print("(PV cost = opex + straight-line depreciation of new hardware; PV cash = opex + capex as paid)")
    base, best = results["5-year age"], results["TCO-optimized"]
    over = [f"{p} year {y}" for p, res in results.items() for y in res.over_budget]
    print(f"\nTCO-optimized vs 5-year age rule: PV cost {k(best.pv_cost - base.pv_cost)}, "
          f"capex {k(sum(y.spent for y in best.years) - sum(y.spent for y in base.years))}, "
          f"exit run-rate {k(best.exit_opex - base.exit_opex)}/yr")
    print(f"over budget: {', '.join(over) if over else 'none'}")

if __name__ == "__main__":
    main()
