"""Synthetic SMART-like fleet snapshot. Failure in the next 30 days is driven by a hidden hazard. Run: python -m disk_failure.synth"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

MODELS = {"HX-8T": 0.0, "HX-12T": 0.35, "SG-16T": -0.2}  # model-level reliability differences (log-odds)
FIELDS = ["serial", "model", "power_on_hours", "temperature_c", "reallocated_sectors", "pending_sectors",
          "uncorrectable_errors", "crc_errors", "seek_error_rate", "failed_30d"]


def drive(rng: random.Random, i: int) -> dict:
    model = rng.choice(list(MODELS))
    hours = int(rng.uniform(500, 52_000))
    temp = round(rng.gauss(36, 4), 1)
    degrading = rng.random() < 0.06  # a small share of drives are on their way out
    realloc = int(rng.expovariate(1 / 40)) if degrading and rng.random() < 0.8 else (int(rng.expovariate(1 / 3)) if rng.random() < 0.08 else 0)
    pending = int(rng.expovariate(1 / 6)) if degrading and rng.random() < 0.6 else (1 if rng.random() < 0.02 else 0)
    uncorr = int(rng.expovariate(1 / 3)) if degrading and rng.random() < 0.5 else 0
    crc = int(rng.expovariate(1 / 5)) if rng.random() < 0.1 else 0  # cabling noise, unrelated to the platters
    seek = round(max(0.0, rng.gauss(0.6 if degrading else 0.3, 0.15)), 3)
    z = (-5.2 + MODELS[model] + 0.55 * math.log1p(realloc) + 0.7 * math.log1p(pending) + 0.6 * math.log1p(uncorr)
         + 2.0 * (seek - 0.3) + 0.25 * (hours / 10_000) + 0.06 * (temp - 36))
    failed = int(rng.random() < 1 / (1 + math.exp(-z)))
    return {"serial": f"D{i:05d}", "model": model, "power_on_hours": hours, "temperature_c": temp, "reallocated_sectors": realloc,
            "pending_sectors": pending, "uncorrectable_errors": uncorr, "crc_errors": crc, "seek_error_rate": seek, "failed_30d": failed}


def write(path: Path, n: int, seed: int) -> None:
    rng = random.Random(seed)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(drive(rng, i) for i in range(n))


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data"
    write(out / "fleet_history.csv", 4000, seed=22)  # labelled: did the drive fail in the following 30 days?
    write(out / "fleet_today.csv", 300, seed=2022)  # today's snapshot to score (labels kept only for the demo)
