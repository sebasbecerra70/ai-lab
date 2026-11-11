"""Detect KPI anomalies, explain downstream effects, and score against labels."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .decompose import decompose, naive_z, robust_z

METRICS = ["dau", "signups", "conversion_rate", "revenue"]
# revenue ~ dau x conversion_rate x AOV, so an upstream anomaly explains a revenue anomaly
DRIVERS = {"revenue": ["dau", "conversion_rate"]}


@dataclass
class KpiTable:
    days: list[int]
    weekdays: list[str]
    series: dict[str, list[float]]
    labels: set[tuple[int, str]]  # (day, metric) known anomalies, including downstream effects


def load_kpis(path: Path) -> KpiTable:
    days, weekdays, labels = [], [], set()
    series: dict[str, list[float]] = {m: [] for m in METRICS}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            day = int(r["day"])
            days.append(day)
            weekdays.append(r["weekday"])
            for m in METRICS:
                series[m].append(float(r[m]))
            if r["anomaly"]:  # "dau+revenue:login outage" -> every metric the incident moved
                for metric in r["anomaly"].split(":", 1)[0].split("+"):
                    labels.add((day, metric))
    return KpiTable(days, weekdays, series, labels)


@dataclass
class Anomaly:
    day: int
    metric: str
    value: float
    expected: float
    z: float
    explained_by: list[str]

    @property
    def pct_off(self) -> float:
        return self.value / self.expected - 1


def detect(table: KpiTable, threshold: float = 3.5, period: int = 7) -> list[Anomaly]:
    found: list[Anomaly] = []
    for metric in METRICS:
        dec = decompose(table.series[metric], period)
        for i, z in enumerate(robust_z(dec.residual)):
            if abs(z) >= threshold:
                found.append(Anomaly(table.days[i], metric, dec.values[i], dec.expected(i), z, []))
    flagged = {(a.day, a.metric) for a in found}
    for a in found:
        a.explained_by = [d for d in DRIVERS.get(a.metric, []) if (a.day, d) in flagged]
    return sorted(found, key=lambda a: (a.day, METRICS.index(a.metric)))


def detect_naive(table: KpiTable, threshold: float = 3.0) -> list[tuple[int, str]]:
    return [(table.days[i], m) for m in METRICS for i, z in enumerate(naive_z(table.series[m])) if abs(z) >= threshold]


@dataclass
class Score:
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0


def score(flags: set[tuple[int, str]], labels: set[tuple[int, str]]) -> Score:
    return Score(len(flags & labels), len(flags - labels), len(labels - flags))
