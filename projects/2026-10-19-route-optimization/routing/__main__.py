"""CLI: python -m routing [truck_capacity_pallets] [max_route_km]"""
import math
import sys
from pathlib import Path

from . import check, load, load_problem, route_km, solve

DATA = Path(__file__).resolve().parent.parent / "data" / "stops.csv"
PER_KM, PER_TRUCK = 1.85, 240.0  # fuel + maintenance per km; driver day + truck lease per route


def main() -> None:
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 18
    max_km = float(sys.argv[2]) if len(sys.argv) > 2 else 110.0
    p = load_problem(DATA, cap, max_km if max_km > 0 else math.inf)
    demand = sum(s.demand for s in p.stops)
    print(f"{len(p.stops)} stops, {demand} pallets, trucks of {cap} pallets, max {max_km:.0f} km/route "
          f"(lower bound {math.ceil(demand / cap)} trucks)\n")
    print(f"{'method':<15}{'trucks':>7}{'km':>8}{'cost/day':>10}  feasible")
    sols = [solve(p, m) for m in ("nearest", "nearest+2opt", "savings", "savings+2opt")]
    for s in sols:
        print(f"{s.method:<15}{s.trucks:>7}{s.km:>8.1f}{s.cost(PER_KM, PER_TRUCK):>10,.0f}  {'yes' if not check(p, s) else check(p, s)}")
    base, best = sols[0], sols[-1]
    saved = base.cost(PER_KM, PER_TRUCK) - best.cost(PER_KM, PER_TRUCK)
    print(f"\nsavings vs nearest-neighbour: {base.km - best.km:.1f} km and ${saved:,.0f}/day (~${saved * 250:,.0f}/yr over 250 days)\n")
    for i, r in enumerate(best.routes, 1):
        print(f"truck {i}: {load(list(r)):>2}/{cap} pallets {route_km(p.depot, list(r)):>5.1f} km  DC -> {' -> '.join(s.id for s in r)} -> DC")


if __name__ == "__main__":
    main()
