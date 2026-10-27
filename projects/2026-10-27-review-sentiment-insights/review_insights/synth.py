"""Generate synthetic app-store style reviews for a smart thermostat. Run: python -m review_insights.synth"""
from __future__ import annotations

import csv
import random
from pathlib import Path

PHRASES = {
    "install": (["Installation took ten minutes and the wiring guide was clear.", "Setup was easy, even for my old furnace."],
                ["Installation was a nightmare, the wiring diagram did not match my system.", "Setup failed twice and I had to call an electrician."]),
    "app": (["The app is clean and easy to use.", "Love the app, the energy reports are great."],
            ["The app is slow and crashes when I open the schedule.", "The new app update is confusing and buggy.", "App keeps logging me out, very frustrating."]),
    "wifi": (["It stays connected without problems.", "Wifi connection has been solid."],
             ["It drops off wifi every few days and the schedule stops working.", "Constant wifi disconnects, I have to reboot it weekly.", "Never stays connected to my router."]),
    "battery": (["Battery lasts for months.", "Battery life is excellent."],
                ["The battery dies in three weeks.", "Battery drains fast and the screen goes blank."]),
    "accuracy": (["Keeps the house at exactly the right temperature.", "Temperature readings are accurate."],
                 ["The temperature reading is off by three degrees.", "It is not accurate, the house is always too cold."]),
    "support": (["Support replied within an hour and fixed it.", "Customer service was helpful and friendly."],
                ["Support never answered my ticket.", "Customer service was useless and rude.", "Waited two weeks for a support reply."]),
    "price": (["Great value for the price.", "Worth every penny, it paid for itself."],
              ["Too expensive for what it does.", "The subscription for basic features is a rip off."]),
    "schedule": (["Scheduling is simple and saves me money.", "The smart schedule learned our routine quickly."],
                 ["The schedule randomly resets.", "Scheduling is not intuitive at all."]),
}
# How often each aspect comes up, and how often mentions are negative: this is the "truth" the analysis should recover.
FREQ = {"install": 0.25, "app": 0.35, "wifi": 0.3, "battery": 0.12, "accuracy": 0.15, "support": 0.18, "price": 0.15, "schedule": 0.2}
NEG = {"install": 0.35, "app": 0.55, "wifi": 0.75, "battery": 0.4, "accuracy": 0.3, "support": 0.6, "price": 0.45, "schedule": 0.35}
OPENERS_POS = ["Really happy with this thermostat.", "Five stars from me.", ""]
OPENERS_NEG = ["Very disappointed.", "Would not recommend.", ""]


def review(rng: random.Random, i: int) -> dict:
    aspects = [a for a in FREQ if rng.random() < FREQ[a]] or [rng.choice(list(FREQ))]
    clauses, net = [], 0
    for a in aspects:
        neg = rng.random() < NEG[a]
        clauses.append(rng.choice(PHRASES[a][1] if neg else PHRASES[a][0]))
        net += -1 if neg else 1
    opener = rng.choice(OPENERS_NEG if net < 0 else OPENERS_POS)
    rating = max(1, min(5, round(3 + 1.2 * net + rng.gauss(0, 0.6))))
    return {"id": f"R{i:03d}", "rating": rating, "text": " ".join(x for x in [opener, *clauses] if x)}


if __name__ == "__main__":
    rng = random.Random(23)
    out = Path(__file__).resolve().parent.parent / "data" / "reviews.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "rating", "text"])
        w.writeheader()
        w.writerows(review(rng, i) for i in range(1, 181))
