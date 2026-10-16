"""CLI: python -m rack_placement [strategy]  -- compares heuristics and prints the chosen plan."""
import sys
from pathlib import Path

from . import STRATEGIES, Placer, evaluate, load_racks, load_servers, validate

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    chosen = sys.argv[1] if len(sys.argv) > 1 else "auto"
    servers = load_servers(DATA / "servers.csv")
    placer = Placer(load_racks(DATA / "racks.csv"), servers)
    print(f"{len(servers)} servers ({sum(s.u for s in servers)}U, {sum(s.kw for s in servers):.1f} kW) "
          f"into {len(placer.base_racks)} racks across rows {', '.join(placer.rows)}\n")
    print(f"{'strategy':<22}{'racks':>6}{'new':>5}{'unplaced':>9}{'stranded kW':>13}{'stranded U':>12}{'peak util':>11}")
    plans = {}
    for strat in STRATEGIES:
        for consolidate in (False, True) if strat != "worst_fit" else (False,):
            plan = placer.place(strat, consolidate=consolidate)
            m = evaluate(plan, servers)
            name = strat + ("+drain" if consolidate else "")
            plans[name] = (plan, m)
            print(f"{name:<22}{m.racks_used:>6}{m.new_racks_opened:>5}{m.unplaced:>9}{m.stranded_kw:>13.2f}"
                  f"{m.stranded_u:>12}{m.max_rack_util:>10.0%}")
    print(f"{'lower bound':<22}{m.lower_bound_racks:>6}")

    if chosen == "auto":  # fewest unplaced, then fewest racks, then least stranded power
        key = min(plans, key=lambda k: (plans[k][1].unplaced, plans[k][1].racks_used, plans[k][1].stranded_kw))
    else:
        key = chosen if chosen in plans else f"{chosen}+drain"
    plan = plans[key][0]
    print(f"\nplan: {key}  (constraint violations: {len(validate(plan, placer))})")
    for r in plan.racks:
        if not r.servers:
            continue
        names = ", ".join(s.id for s in r.servers)
        print(f"  {r.id}  {r.u_capacity - r.free_u:>2}/{r.u_capacity}U  {r.kw_capacity - r.free_kw:>4.1f}/{r.kw_capacity} kW  {names}")
    for s, why in plan.unplaced:
        print(f"  UNPLACED {s.id}: {why}")
    empty = [r.id for r in plan.racks if not r.in_use]
    print(f"  left empty for future demand: {', '.join(empty) or 'none'}")


if __name__ == "__main__":
    main()
