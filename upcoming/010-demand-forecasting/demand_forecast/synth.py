"""Generate four years of weekly demand for four SKU archetypes.

python -m demand_forecast.synth > data/weekly_demand.csv
"""
from __future__ import annotations

import math
import random
import sys

WEEKS = 208


def generate(seed: int = 5) -> dict[str, list[int]]:
    rng = random.Random(seed)
    season = [math.sin(2 * math.pi * (w - 10) / 52) for w in range(WEEKS)]
    return {
        # Seasonal: summer peak, e.g. pallet wrap for a beverage distributor.
        "SKU-STRETCH-WRAP": [max(0, round(400 + 160 * s + rng.gauss(0, 25))) for s in season],
        # Trending: steady growth from a new customer ramp.
        "SKU-LABEL-4X6": [max(0, round(220 + 2.2 * w + rng.gauss(0, 18))) for w in range(WEEKS)],
        # Stable: replenishment of a staple.
        "SKU-GLOVES-L": [max(0, round(150 + rng.gauss(0, 12))) for _ in range(WEEKS)],
        # Intermittent: a spare part with lumpy, infrequent orders.
        "SKU-SPARE-MOTOR": [rng.choice([1, 2, 2, 3, 4]) if rng.random() < 0.22 else 0 for _ in range(WEEKS)],
    }


if __name__ == "__main__":
    sys.stdout.write("sku,week,units\n")
    for sku, series in generate().items():
        for w, units in enumerate(series, 1):
            sys.stdout.write(f"{sku},{w},{units}\n")
