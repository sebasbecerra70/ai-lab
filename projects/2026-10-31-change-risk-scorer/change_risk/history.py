"""Change failure rates by type from past changes, smoothed so a type with 3 records doesn't read as 0% risk."""
from __future__ import annotations

import csv
from pathlib import Path

PRIOR_FAIL, PRIOR_OK = 1.0, 9.0  # Beta(1, 9): a 10% failure rate is the starting assumption for any change type


def failure_rates(rows: list[dict], prior: tuple[float, float] = (PRIOR_FAIL, PRIOR_OK)) -> dict[str, float]:
    """Posterior mean of Beta(prior) after observing failures. Rolled-back changes count as failures:
    the change did not do what it said and someone spent the window undoing it."""
    counts: dict[str, list[int]] = {}
    for r in rows:
        c = counts.setdefault(r["type"], [0, 0])
        c[0] += r["outcome"] in ("failed", "rolled_back")
        c[1] += 1
    a, b = prior
    return {t: (fails + a) / (n + a + b) for t, (fails, n) in counts.items()}


def load_history(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))
