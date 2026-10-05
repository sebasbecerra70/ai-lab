"""Load shipment CSVs and turn rows into model features."""
from __future__ import annotations

import csv
from pathlib import Path

NUMERIC = ("distance_km", "planned_days", "weather_index", "carrier_otp_90d", "schedule_slack")
CATEGORICAL = ("lane", "carrier", "mode", "ship_dow", "peak_season", "cross_border")
KM_PER_DAY = 700  # a single driver's practical daily range; used to judge whether the plan is tight


def load_rows(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def featurize(row: dict) -> dict:
    """Raw CSV row -> feature dict. Derived features carry the domain knowledge."""
    dist = float(row["distance_km"])
    planned = float(row["planned_days"])
    origin, dest = row["lane"].split("-")
    return {
        "distance_km": dist,
        "planned_days": planned,
        "weather_index": float(row["weather_index"]),
        "carrier_otp_90d": float(row["carrier_otp_90d"]),
        # < 1.0 means the planned transit is shorter than a driver can physically cover
        "schedule_slack": round(planned * KM_PER_DAY / dist, 3),
        "lane": row["lane"],
        "carrier": row["carrier"],
        "mode": row["mode"],
        "ship_dow": row["ship_dow"],
        "peak_season": str(row["peak_season"]),
        "cross_border": "yes" if {origin, dest} & {"MTY", "TOR"} else "no",
    }


def dataset(rows: list[dict]) -> tuple[list[dict], list[int]]:
    return [featurize(r) for r in rows], [int(r["delayed"]) for r in rows]


def time_split(rows: list[dict], test_frac: float = 0.25) -> tuple[list[dict], list[dict]]:
    """Train on older weeks, test on the most recent ones: no peeking at the future."""
    ordered = sorted(rows, key=lambda r: (int(r["week"]), r["shipment_id"]))
    cut = int(len(ordered) * (1 - test_frac))
    return ordered[:cut], ordered[cut:]
