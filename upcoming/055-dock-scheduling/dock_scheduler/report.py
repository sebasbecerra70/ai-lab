"""Plain-text tables for the CLI."""
from __future__ import annotations

from .model import Door, Kpis, Plan, clock, simulate


def kpi_table(rows: list[tuple[str, Kpis]]) -> str:
    out = [f"{'plan':<14}{'avg wait':>9}{'max wait':>9}{'reefer':>8}{'>60 min':>8}{'detention':>10}{'overtime':>9}{'cost':>8}"]
    for name, k in rows:
        out.append(f"{name:<14}{k.avg_wait:>7.0f}m {k.max_wait:>7.0f}m {k.reefer_avg_wait:>6.0f}m {k.over_60:>7}{'$' + format(k.detention, ',.0f'):>10}"
                   f"{k.overtime:>8.0f}m{k.cost:>8.0f}")
    return "\n".join(out)


def door_table(plan: Plan, doors: dict[str, Door]) -> str:
    out = []
    slots = simulate(plan, doors)
    for name in plan:
        mine = [s for s in slots if s.door == name]
        cells = [f"{s.truck.name}{'*' if s.truck.reefer else ''}@{clock(s.start)}"
                 + (f"(+{s.wait:.0f})" if s.wait >= 1 else "") for s in mine]
        d = doors[name]
        tag = "reefer" if d.reefer else "dry"
        out.append(f"{name} {tag:<6} {d.min_per_pallet:.1f}m/plt  " + " ".join(cells))
    return "\n".join(out)
