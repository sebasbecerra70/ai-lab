"""Synthetic B2B lead generator with a known ground truth, so we can check the model recovers it.

python -m lead_scoring.synth > data/leads.csv
"""
from __future__ import annotations

import csv
import math
import random
import sys

INDUSTRIES = ["logistics", "manufacturing", "retail", "healthcare", "education"]
INDUSTRY_LIFT = {"logistics": 0.9, "manufacturing": 0.6, "retail": 0.1, "healthcare": -0.2, "education": -0.8}
SOURCES = ["inbound", "outbound", "event", "partner"]
SOURCE_LIFT = {"inbound": 0.5, "outbound": -0.6, "event": 0.0, "partner": 0.7}
COLUMNS = ["lead_id", "company", "industry", "source", "employees", "web_visits_30d", "pricing_page_views",
           "email_opens_30d", "demo_requested", "days_since_last_touch", "converted"]


def generate(n: int = 400, seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(1, n + 1):
        industry, source = rng.choice(INDUSTRIES), rng.choice(SOURCES)
        employees = int(math.exp(rng.uniform(math.log(20), math.log(20000))))
        visits = min(60, int(rng.expovariate(1 / 6)))
        pricing = min(visits, int(rng.expovariate(1 / 1.2)))
        opens = int(rng.expovariate(1 / 4))
        demo = 1 if rng.random() < 0.12 + 0.03 * pricing else 0
        stale = int(rng.expovariate(1 / 20))
        z = (-3.0 + INDUSTRY_LIFT[industry] + SOURCE_LIFT[source] + 0.35 * math.log10(employees)
             + 0.05 * visits + 0.45 * pricing + 0.04 * opens + 1.6 * demo - 0.04 * stale)
        converted = 1 if rng.random() < 1 / (1 + math.exp(-z)) else 0
        rows.append({"lead_id": f"L{i:04d}", "company": f"Company {i:04d}", "industry": industry, "source": source,
                     "employees": employees, "web_visits_30d": visits, "pricing_page_views": pricing,
                     "email_opens_30d": opens, "demo_requested": demo, "days_since_last_touch": stale,
                     "converted": converted})
    return rows


if __name__ == "__main__":
    w = csv.DictWriter(sys.stdout, fieldnames=COLUMNS)
    w.writeheader()
    w.writerows(generate())
