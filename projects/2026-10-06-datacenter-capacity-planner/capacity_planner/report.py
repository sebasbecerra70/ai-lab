"""Plain-text capacity report for a weekly ops review."""
from __future__ import annotations

from .model import Forecast, Hall, Site, facility_load_kw, headroom, pue


def _fmt_month(m: int | None, horizon: int) -> str:
    if m is None:
        return f">{horizon}mo"
    return "NOW" if m == 0 else f"{m}mo"


def headroom_table(halls: list[Hall], site: Site) -> str:
    lines = [f"{'hall':<5}{'power kW':>10}{'cooling kW':>12}{'racks':>8}  binding (util)"]
    for h in halls:
        hr = headroom(h, site.safety_margin)
        util = hr.utilization[hr.binding]
        lines.append(f"{h.name:<5}{hr.power_kw:>10.0f}{hr.cooling_kw:>12.0f}{hr.racks:>8.0f}  {hr.binding} ({util:.0%})")
    total = facility_load_kw(halls, site)
    lines.append(f"site: facility load {total:.0f} kW of {site.utility_feed_kw:.0f} kW feed, PUE {pue(halls, site):.2f}")
    return "\n".join(lines)


def forecast_table(forecasts: list[Forecast], horizon: int) -> str:
    lines = []
    for f in forecasts:
        wall = f.first_wall()
        headline = (f"first wall: hall {wall[0]} {wall[1]} in {_fmt_month(wall[2], horizon)}" if wall
                    else f"no wall within {horizon} months")
        lines.append(f"[{f.scenario}] {headline}; utility feed {_fmt_month(f.utility_month, horizon)}; "
                     f"PUE by year {f.pue_by_year}")
        for hall, cs in f.exhaustion.items():
            cells = "  ".join(f"{c}={_fmt_month(m, horizon)}" for c, m in cs.items())
            lines.append(f"    {hall}: {cells}")
    return "\n".join(lines)
