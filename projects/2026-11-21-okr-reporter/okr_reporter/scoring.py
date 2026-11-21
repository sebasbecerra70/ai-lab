"""OKR math: progress from baseline to target, pace vs. time elapsed, and a trend forecast to quarter end."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class KR:
    id: str
    title: str
    metric: str
    baseline: float
    target: float
    unit: str
    weight: float
    current: float = 0.0
    progress: float = 0.0     # 0..1 of the way from baseline to target (direction-aware)
    expected: float = 0.0     # progress a linear plan would have reached by now
    forecast: float = 0.0     # projected metric value at quarter end from the recent trend
    projected: float = 0.0    # projected progress at quarter end, 0..1+
    status: str = ""          # on track | at risk | off track | done


@dataclass
class Objective:
    id: str
    title: str
    krs: list[KR] = field(default_factory=list)

    @property
    def score(self) -> float:
        return sum(k.weight * min(k.progress, 1.0) for k in self.krs) / sum(k.weight for k in self.krs)

    @property
    def projected(self) -> float:
        return sum(k.weight * min(k.projected, 1.0) for k in self.krs) / sum(k.weight for k in self.krs)


def biggest_gap(objectives: list[Objective]) -> KR | None:
    """The KR whose shortfall costs the most score: weight x (1 - projected), among those not on track."""
    lagging = [k for o in objectives for k in o.krs if k.status in ("off track", "at risk")]
    return max(lagging, key=lambda k: k.weight * (1 - min(k.projected, 1.0)), default=None)


def progress(baseline: float, target: float, value: float) -> float:
    """Works for both directions: latency 640 -> 300 at 470 is 50% done."""
    if target == baseline:
        return 1.0
    return max(0.0, (value - baseline) / (target - baseline))


def trend(values: list[float], window: int = 4) -> float:
    """Least-squares slope per week over the last `window` points (robust to one noisy week)."""
    ys = values[-window:]
    n = len(ys)
    if n < 2:
        return 0.0
    xbar, ybar = (n - 1) / 2, sum(ys) / n
    return sum((x - xbar) * (y - ybar) for x, y in enumerate(ys)) / sum((x - xbar) ** 2 for x in range(n))


def classify(projected: float, prog: float) -> str:
    if prog >= 1.0:
        return "done"
    if projected >= 0.9:
        return "on track"
    if projected >= 0.7:
        return "at risk"
    return "off track"


def score(okr_path: Path, metrics_path: Path) -> tuple[dict, list[Objective], int]:
    cfg = json.loads(okr_path.read_text())
    with open(metrics_path) as f:
        rows = list(csv.DictReader(f))
    series = {k: [float(r[k]) for r in rows] for k in rows[0] if k != "week"}
    week, total = int(rows[-1]["week"]), cfg["weeks_in_quarter"]
    objectives = []
    for o in cfg["objectives"]:
        obj = Objective(o["id"], o["title"])
        for k in o["key_results"]:
            kr = KR(**k)
            vals = series[kr.metric]
            kr.current = vals[-1]
            kr.progress = progress(kr.baseline, kr.target, kr.current)
            kr.expected = week / total
            kr.forecast = kr.current + trend(vals) * (total - week)
            kr.projected = progress(kr.baseline, kr.target, kr.forecast)
            kr.status = classify(kr.projected, kr.progress)
            obj.krs.append(kr)
        objectives.append(obj)
    return cfg, objectives, week


def fmt(kr: KR, value: float) -> str:
    if kr.unit == "%":
        return f"{value * 100:.1f}%"
    num = f"{value:.1f}" if abs(value) < 10 and value != int(value) else f"{value:,.0f}"
    return f"{num}{(' ' + kr.unit) if kr.unit else ''}"
