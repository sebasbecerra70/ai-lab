"""Routing metrics that matter to a service desk: auto-route rate, accuracy when routed, triage catches."""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .router import TRIAGE, CentroidRouter

KEYWORDS = {  # the rules a service desk usually starts with, as a baseline
    "network": ["wifi", "vpn", "network", "internet"],
    "access": ["password", "access", "locked", "login", "account"],
    "hardware": ["laptop", "monitor", "printer", "broken", "screen"],
    "software": ["install", "crash", "error", "update", "license"],
    "security": ["phishing", "suspicious", "stolen", "virus"],
}


def load(path: Path) -> list[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))


def keyword_route(text: str) -> str:
    t = text.lower()
    hits = Counter({q: sum(w in t for w in ws) for q, ws in KEYWORDS.items()})
    q, n = hits.most_common(1)[0]
    return q if n else TRIAGE


@dataclass
class Metrics:
    auto_rate: float          # share of in-scope tickets routed without a human
    routed_accuracy: float    # accuracy on the tickets we did route
    end_to_end: float         # in-scope tickets that land in the right queue with no human touch
    misroutes: int            # in-scope tickets sent to the wrong queue (the expensive error)
    off_topic_caught: float   # off-topic tickets sent to triage instead of an IT queue


def metrics(preds: list[str], truth: list[str]) -> Metrics:
    in_scope = [(p, t) for p, t in zip(preds, truth) if t != TRIAGE]
    off = [p for p, t in zip(preds, truth) if t == TRIAGE]
    routed = [(p, t) for p, t in in_scope if p != TRIAGE]
    correct = sum(p == t for p, t in routed)
    return Metrics(
        auto_rate=len(routed) / len(in_scope),
        routed_accuracy=correct / max(len(routed), 1),
        end_to_end=correct / len(in_scope),
        misroutes=len(routed) - correct,
        off_topic_caught=sum(p == TRIAGE for p in off) / max(len(off), 1),
    )


def sweep(router: CentroidRouter, rows: list[dict], thresholds: list[float]) -> list[tuple[float, Metrics]]:
    """Trade auto-route rate against misroutes by moving the similarity threshold."""
    out = []
    saved = router.min_score
    for th in thresholds:
        router.min_score = th
        out.append((th, metrics([router.route(r["text"]).queue for r in rows], [r["queue"] for r in rows])))
    router.min_score = saved
    return out
