"""CLI: python -m log_anomaly [syslog.txt]"""
import re
import sys
from collections import defaultdict
from pathlib import Path

from . import Drain, detect, incidents, parse

DATA = Path(__file__).resolve().parent.parent / "data" / "syslog.txt"
WINDOW = 600


def hhmm(sec: int) -> str:
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA
    drain = Drain()
    events = parse(path, drain)
    print(f"{len(events):,} lines -> {len(drain.clusters)} templates (baseline 00:00-04:00, 10-minute windows)\n")
    for c in sorted(drain.clusters, key=lambda c: -c.size):
        print(f"  T{c.id:<3}{c.size:>6}  {c.text}")

    kw = re.compile(r"fail|error|down|warning|out of range", re.I)
    raw = path.read_text().splitlines()
    quiet = sum(bool(kw.search(ln)) for ln in raw if ln < "04:00")
    print(f"\nfor comparison, a keyword alert (fail|error|down|warning) fires {quiet} times in the quiet baseline hours")

    found = detect(events, drain, window=WINDOW)
    groups = incidents(found)
    print(f"\n{len(found)} anomalous (window, template) signals -> {len(groups)} incident(s)")
    for g in groups:
        start, end = g[0].window * WINDOW, (g[-1].window + 1) * WINDOW
        print(f"\nINCIDENT {hhmm(start)}-{hhmm(end)}")
        merged = defaultdict(lambda: {"count": 0, "windows": 0, "hosts": set(), "expected": 0.0})
        for a in g:
            m = merged[(a.kind, a.cluster, a.template)]
            m["count"] += a.count
            m["windows"] += 1
            m["hosts"] |= set(a.hosts)
            m["expected"] = a.expected
        for (kind, cid, tpl), m in sorted(merged.items(), key=lambda kv: {"new": 0, "silent": 1, "burst": 2}[kv[0][0]]):
            hosts = ", ".join(sorted(m["hosts"]))
            if kind == "new":
                detail = f"{m['count']} lines, never seen in baseline"
            elif kind == "silent":
                detail = f"0 lines for {m['windows']} windows (baseline {m['expected']:.1f}/window)"
            else:
                detail = f"{m['count']} lines over {m['windows']} windows (baseline {m['expected']:.1f}/window)"
            print(f"  {kind.upper():<7}T{cid:<3}{tpl[:58]:<58}  {detail}  [{hosts}]")


if __name__ == "__main__":
    main()
