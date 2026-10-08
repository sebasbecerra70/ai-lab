"""Turn raw lead rows into a numeric design matrix: log transforms, one-hot encoding, standardization."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

NUMERIC = ["log_employees", "web_visits_30d", "pricing_page_views", "email_opens_30d", "demo_requested",
           "days_since_last_touch"]
CATEGORICAL = {"industry": ["logistics", "manufacturing", "retail", "healthcare", "education"],
               "source": ["inbound", "outbound", "event", "partner"]}
# Drop one level per categorical as the baseline, otherwise the one-hots are collinear with the intercept.
BASELINE = {"industry": "retail", "source": "event"}


def load_leads(path: str | Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def raw_features(row: dict) -> dict[str, float]:
    feats = {
        "log_employees": math.log10(max(1.0, float(row["employees"]))),
        "web_visits_30d": float(row["web_visits_30d"]),
        "pricing_page_views": float(row["pricing_page_views"]),
        "email_opens_30d": float(row["email_opens_30d"]),
        "demo_requested": float(row["demo_requested"]),
        "days_since_last_touch": float(row["days_since_last_touch"]),
    }
    for col, levels in CATEGORICAL.items():
        if row[col] not in levels:
            raise ValueError(f"unknown {col} '{row[col]}'")
        for level in levels:
            if level != BASELINE[col]:
                feats[f"{col}={level}"] = 1.0 if row[col] == level else 0.0
    return feats


@dataclass
class Standardizer:
    names: list[str] = field(default_factory=list)
    mean: dict[str, float] = field(default_factory=dict)
    std: dict[str, float] = field(default_factory=dict)

    def fit(self, rows: list[dict[str, float]]) -> "Standardizer":
        self.names = list(rows[0])
        n = len(rows)
        for name in self.names:
            vals = [r[name] for r in rows]
            mu = sum(vals) / n
            sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / n)
            self.mean[name], self.std[name] = mu, sd or 1.0
        return self

    def transform(self, row: dict[str, float]) -> list[float]:
        return [(row[name] - self.mean[name]) / self.std[name] for name in self.names]
