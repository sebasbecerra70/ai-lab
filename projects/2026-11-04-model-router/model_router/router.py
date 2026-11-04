"""Route prompts by predicted difficulty and evaluate the cost/quality trade-off."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .classifier import DifficultyClassifier
from .llm import LLMClient


@dataclass(frozen=True)
class ModelTier:
    name: str
    usd_per_mtok_in: float
    usd_per_mtok_out: float
    quality_easy: float  # probability of an acceptable answer on easy prompts
    quality_hard: float

    def cost(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.usd_per_mtok_in + tokens_out * self.usd_per_mtok_out) / 1e6


# List prices (Haiku 4.5, Sonnet 5.5) and illustrative acceptance rates; replace with your eval results.
SMALL = ModelTier("small", 1.0, 5.0, quality_easy=0.96, quality_hard=0.58)
LARGE = ModelTier("large", 2.0, 10.0, quality_easy=0.97, quality_hard=0.93)


def load_jsonl(path: Path) -> tuple[list[str], list[int]]:
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return [r["text"] for r in rows], [1 if r["label"] == "hard" else 0 for r in rows]


def estimate_tokens(text: str, hard: bool) -> tuple[int, int]:
    """Rough token estimate: ~0.75 words/token in, longer answers for hard prompts."""
    tokens_in = int(len(text.split()) / 0.75) + 200  # +system prompt
    return tokens_in, 900 if hard else 120


@dataclass
class RouteDecision:
    tier: ModelTier
    p_hard: float


class Router:
    def __init__(self, clf: DifficultyClassifier, threshold: float = 0.5,
                 small: ModelTier = SMALL, large: ModelTier = LARGE):
        self.clf, self.threshold, self.small, self.large = clf, threshold, small, large

    def decide(self, text: str) -> RouteDecision:
        p = self.clf.predict_proba(text)
        return RouteDecision(self.large if p >= self.threshold else self.small, p)

    def run(self, text: str, clients: dict[str, LLMClient]) -> tuple[RouteDecision, str]:
        d = self.decide(text)
        return d, clients[d.tier.name].complete("Answer concisely and accurately.", text)


@dataclass
class PolicyReport:
    policy: str
    cost_usd: float
    expected_quality: float
    pct_large: float


def evaluate(policy: str, choose, texts: list[str], labels: list[int],
             daily_volume: int = 100_000) -> PolicyReport:
    """Expected cost per day (scaled to daily_volume) and quality for a routing policy."""
    cost = quality = n_large = 0.0
    for text, y in zip(texts, labels):
        tier = choose(text)
        tin, tout = estimate_tokens(text, bool(y))
        cost += tier.cost(tin, tout)
        quality += tier.quality_hard if y else tier.quality_easy
        n_large += tier.name == "large"
    n = len(texts)
    return PolicyReport(policy, cost / n * daily_volume, quality / n, n_large / n)


def frontier(clf: DifficultyClassifier, texts: list[str], labels: list[int],
             thresholds=(0.2, 0.35, 0.5, 0.65, 0.8)) -> list[PolicyReport]:
    truth = dict(zip(texts, labels))
    reports = [
        evaluate("always-small", lambda t: SMALL, texts, labels),
        evaluate("always-large", lambda t: LARGE, texts, labels),
        evaluate("oracle", lambda t: LARGE if truth[t] else SMALL, texts, labels),
    ]
    for th in thresholds:
        r = Router(clf, th)
        reports.append(evaluate(f"router@{th:.2f}", lambda t, r=r: r.decide(t).tier, texts, labels))
    return reports


def accuracy(clf: DifficultyClassifier, texts: list[str], labels: list[int], th: float = 0.5) -> float:
    return sum((clf.predict_proba(t) >= th) == bool(y) for t, y in zip(texts, labels)) / len(texts)
