"""Data model and loaders for jobs and the hourly grid signal."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Job:
    job_id: str
    team: str
    power_kw: float
    duration_h: int
    release_h: int
    deadline_h: int  # job must finish by the end of hour deadline_h - 1
    preemptible: bool

    @property
    def slack(self) -> int:
        return self.deadline_h - self.release_h - self.duration_h

    @property
    def energy_mwh(self) -> float:
        return self.power_kw * self.duration_h / 1000


@dataclass(frozen=True)
class GridHour:
    hour: int
    price_usd_mwh: float
    carbon_g_kwh: float


def load_jobs(path: Path) -> list[Job]:
    with open(path, newline="") as f:
        return [
            Job(r["job_id"], r["team"], float(r["power_kw"]), int(r["duration_h"]),
                int(r["release_h"]), int(r["deadline_h"]), r["preemptible"].strip().lower() == "yes")
            for r in csv.DictReader(f)
        ]


def load_grid(path: Path) -> list[GridHour]:
    with open(path, newline="") as f:
        return [GridHour(int(r["hour"]), float(r["price_usd_mwh"]), float(r["carbon_g_kwh"]))
                for r in csv.DictReader(f)]
