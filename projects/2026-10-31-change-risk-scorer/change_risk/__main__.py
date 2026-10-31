"""CLI: python -m change_risk [CHG-id ...]   (no ids = the whole CAB agenda)"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import failure_rates, load_changes, load_history, load_topology, score_all


def main() -> None:
    data = Path(__file__).resolve().parent.parent / "data"
    topo = load_topology(data / "topology.json")
    rates = failure_rates(load_history(data / "history.csv"))
    cal = json.loads((data / "calendar.json").read_text())
    changes = load_changes(data / "changes.json")
    if len(sys.argv) > 1:
        changes = [c for c in changes if c.id in sys.argv[1:]]
    results = score_all(changes, topo, rates, cal)

    print("Failure rate by change type (Beta(1,9) smoothed): "
          + ", ".join(f"{t} {p:.0%}" for t, p in sorted(rates.items(), key=lambda kv: -kv[1])))
    print(f"\nCAB agenda: {len(results)} changes")
    print(f"{'change':<10}{'when':<17}{'P(fail)':>8}{'L':>3}{'I':>3}{'risk':>6}  recommendation")
    for a in results:
        c = a.change
        print(f"{c.id:<10}{c.start.strftime('%a %d %b %H:%M'):<17}{a.failure_prob:>8.0%}{a.likelihood:>3}{a.impact:>3}"
              f"{a.risk:>6}  {a.recommendation}")

    for a in results:
        c = a.change
        down = sorted(a.outage.down - set(c.targets))
        print(f"\n{c.id} {c.title} [{c.type}] -> {a.recommendation}")
        print(f"  blast radius if it fails: {', '.join(down) if down else 'target only'}")
        if a.outage.degraded:
            print(f"  loses redundancy: {', '.join(sorted(a.outage.degraded))}")
        for b in a.blockers:
            print(f"  BLOCKER: {b}")
        for cond in a.conditions:
            print(f"  condition: {cond}")


if __name__ == "__main__":
    main()
