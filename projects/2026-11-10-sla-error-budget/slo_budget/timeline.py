"""Synthesize a per-minute request timeline from a traffic profile plus incident records."""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Incident:
    incident_id: str
    start: int  # minute offset from the start of the window
    duration: int
    error_rate: float
    description: str

    @property
    def end(self) -> int:
        return self.start + self.duration


def load_incidents(path: Path) -> list[Incident]:
    with open(path, newline="") as f:
        return [Incident(r["incident_id"], int(r["start_minute"]), int(r["duration_min"]),
                         float(r["error_rate"]), r["description"]) for r in csv.DictReader(f)]


def load_config(path: Path) -> dict:
    return json.loads(Path(path).read_text())


class Timeline:
    """Expected request and error counts per minute, with O(1) window sums via prefix arrays."""

    def __init__(self, total: list[float], bad: list[float]):
        self.total, self.bad = total, bad
        self._pt, self._pb = [0.0], [0.0]
        for t, b in zip(total, bad):
            self._pt.append(self._pt[-1] + t)
            self._pb.append(self._pb[-1] + b)

    def __len__(self) -> int:
        return len(self.total)

    def window(self, end: int, length: int) -> tuple[float, float]:
        """(bad, total) for minutes [end - length, end)."""
        start = max(0, end - length)
        return self._pb[end] - self._pb[start], self._pt[end] - self._pt[start]

    @classmethod
    def synthesize(cls, cfg: dict, incidents: list[Incident]) -> "Timeline":
        minutes = cfg["window_days"] * 24 * 60
        tr = cfg["traffic_rpm"]
        total, bad = [], []
        rate_at = [cfg["baseline_error_rate"]] * minutes
        for inc in incidents:
            for m in range(inc.start, min(inc.end, minutes)):
                rate_at[m] = max(rate_at[m], inc.error_rate)
        for m in range(minutes):
            hour = (m / 60) % 24
            rpm = tr["mean"] + tr["diurnal_amplitude"] * math.cos(2 * math.pi * (hour - tr["peak_hour"]) / 24)
            total.append(rpm)
            bad.append(rpm * rate_at[m])
        return cls(total, bad)


def incident_cost(tl: Timeline, inc: Incident, baseline_rate: float) -> float:
    """Bad requests attributable to an incident (above the background error rate)."""
    bad, total = tl.window(inc.end, inc.duration)
    return bad - total * baseline_rate
