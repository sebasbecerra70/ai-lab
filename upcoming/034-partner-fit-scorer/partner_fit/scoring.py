"""Normalize partner attributes, compute weighted fit scores, and test rank robustness."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .ahp import AHPResult, ahp_weights


@dataclass
class Partner:
    name: str
    kind: str
    values: dict[str, float]


@dataclass
class Scored:
    partner: Partner
    score: float  # 0-100
    contributions: dict[str, float]  # points contributed by each criterion
    normalized: dict[str, float]  # 0..1 standing on each criterion, higher is better


def load_config(path: Path) -> tuple[dict[str, str], AHPResult]:
    cfg = json.loads(Path(path).read_text())
    directions = {k: v["direction"] for k, v in cfg["criteria"].items()}
    return directions, ahp_weights(list(directions), [tuple(c) for c in cfg["comparisons"]])


def load_partners(path: Path, criteria: list[str]) -> list[Partner]:
    with open(path, newline="") as f:
        return [Partner(r["partner"], r["type"], {c: float(r[c]) for c in criteria}) for r in csv.DictReader(f)]


def normalize(partners: list[Partner], directions: dict[str, str]) -> dict[str, dict[str, float]]:
    """Min-max scale each criterion to 0..1; cost criteria are inverted so higher is always better."""
    out: dict[str, dict[str, float]] = {p.name: {} for p in partners}
    for c, direction in directions.items():
        vals = [p.values[c] for p in partners]
        lo, hi = min(vals), max(vals)
        for p in partners:
            x = 0.5 if hi == lo else (p.values[c] - lo) / (hi - lo)
            out[p.name][c] = 1 - x if direction == "cost" else x
    return out


def score(partners: list[Partner], directions: dict[str, str], weights: dict[str, float]) -> list[Scored]:
    norm = normalize(partners, directions)
    total_w = sum(weights.values())
    ranked = []
    for p in partners:
        contrib = {c: 100 * weights[c] / total_w * norm[p.name][c] for c in directions}
        ranked.append(Scored(p, sum(contrib.values()), contrib, norm[p.name]))
    return sorted(ranked, key=lambda s: (-s.score, s.partner.name))


def explain(s: Scored, k: int = 2) -> str:
    """Strongest = highest standing on the criteria that carry the most weight; weakest = lowest standing."""
    by_standing = sorted(s.normalized, key=lambda c: (-s.normalized[c], -s.contributions[c]))
    weak = min(s.normalized, key=lambda c: (s.normalized[c], -s.contributions[c]))
    return f"strongest on {', '.join(by_standing[:k])}; weakest on {weak}"


@dataclass
class Sensitivity:
    criterion: str
    change: float
    new_leader: str
    leader_changed: bool


def sensitivity(partners: list[Partner], directions: dict[str, str], weights: dict[str, float],
                changes=(-0.5, -0.25, 0.25, 0.5)) -> list[Sensitivity]:
    """Scale one criterion weight at a time by (1 + change) and record who ranks first."""
    leader = score(partners, directions, weights)[0].partner.name
    rows = []
    for c in directions:
        for ch in changes:
            w = dict(weights)
            w[c] = weights[c] * (1 + ch)
            new = score(partners, directions, w)[0].partner.name
            rows.append(Sensitivity(c, ch, new, new != leader))
    return rows
