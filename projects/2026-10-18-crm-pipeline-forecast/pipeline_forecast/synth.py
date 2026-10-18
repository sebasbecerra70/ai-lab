"""Deterministic synthetic CRM data: closed-deal history and the open pipeline. Run: python -m pipeline_forecast.synth"""
from __future__ import annotations

import csv
import random
from pathlib import Path

STAGES = ["Discovery", "Qualified", "Proposal", "Negotiation", "Commit"]
# Chance a fresh deal advances from each stage, and typical days spent there.
ADVANCE = [0.55, 0.62, 0.70, 0.80, 0.90]
DWELL = [14, 18, 21, 14, 9]
ACCOUNTS = ["Acme Logistics", "Brightline Health", "Cobalt Mining", "Delta Freight", "Evergreen Foods", "Fulcrum Bank",
            "Granite Telecom", "Harbor Retail", "Ion Energy", "Juniper Pharma", "Keystone Insurance", "Lumen Labs",
            "Meridian Air", "Northwind Traders", "Orbit Media", "Pinnacle Steel", "Quanta Auto", "Riverbend Utilities"]
OWNERS = ["avery", "jordan", "sam", "taylor"]


def _dwell(rng: random.Random, stage: int, stale: bool) -> int:
    base = rng.expovariate(1 / DWELL[stage])
    return int(base + (DWELL[stage] * rng.uniform(1.5, 3.0) if stale else 0)) + 1


def history(rng: random.Random, n: int = 600) -> list[dict]:
    rows = []
    for i in range(n):
        stage, total_days = 0, 0
        stale = False
        while True:
            # Deals that stall get stuck: they are much less likely to advance.
            stale = rng.random() < 0.25
            days = _dwell(rng, stage, stale)
            total_days += days
            p = ADVANCE[stage] * (0.45 if stale else 1.0)
            advanced = rng.random() < p
            rows.append({"deal_id": f"H{i:04d}", "stage": STAGES[stage], "days_in_stage": days, "won": None, "days_to_close": None, "_t": total_days})
            if not advanced:
                outcome = 0
                break
            if stage == len(STAGES) - 1:
                outcome = 1
                break
            stage += 1
        mine = [r for r in rows if r["deal_id"] == f"H{i:04d}"]
        for r in mine:
            r["won"] = outcome
            r["days_to_close"] = total_days - r["_t"] + r["days_in_stage"]
    for r in rows:
        del r["_t"]
    return rows


def pipeline(rng: random.Random, n: int = 64) -> list[dict]:
    rows = []
    weights = [0.30, 0.25, 0.22, 0.15, 0.08]
    for i in range(n):
        stage = rng.choices(range(len(STAGES)), weights)[0]
        stale = rng.random() < 0.28
        amount = round(rng.lognormvariate(10.9, 0.6) / 500) * 500
        category = "commit" if stage >= 3 else "best_case" if stage == 2 else "pipeline"
        if stale and stage >= 3 and rng.random() < 0.6:
            category = "commit"  # reps rarely downgrade a deal they've already called
        rows.append({
            "deal_id": f"D{i + 1:03d}", "account": rng.choice(ACCOUNTS), "owner": rng.choice(OWNERS), "stage": STAGES[stage],
            "amount": amount, "days_in_stage": _dwell(rng, stage, stale), "rep_category": category,
        })
    return rows


def write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data"
    write(out / "history.csv", history(random.Random(7)))
    write(out / "pipeline.csv", pipeline(random.Random(11)))
