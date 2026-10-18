"""Learn stage conversion, aging decay and close timing from history; forecast the open pipeline."""
from __future__ import annotations

import csv
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .synth import STAGES


def percentile(values: list[float], q: float) -> float:
    s = sorted(values)
    if not s:
        raise ValueError("no values")
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


@dataclass(frozen=True)
class Deal:
    deal_id: str
    account: str
    owner: str
    stage: str
    amount: float
    days_in_stage: int
    rep_category: str


@dataclass(frozen=True)
class StageStats:
    stage: str
    win_rate: float  # P(won | reached stage)
    win_rate_fresh: float
    win_rate_stale: float
    stale_after_days: float  # p75 dwell of deals that went on to win
    won_days_to_close: tuple[int, ...]  # days from entering the stage to close, won deals only

    @property
    def aging_factor(self) -> float:
        return self.win_rate_stale / self.win_rate_fresh if self.win_rate_fresh else 1.0


def load_history(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return [{**r, "days_in_stage": int(r["days_in_stage"]), "won": int(r["won"]), "days_to_close": int(r["days_to_close"])} for r in csv.DictReader(f)]


def load_pipeline(path: Path) -> list[Deal]:
    with open(path, newline="") as f:
        return [Deal(r["deal_id"], r["account"], r["owner"], r["stage"], float(r["amount"]), int(r["days_in_stage"]), r["rep_category"])
                for r in csv.DictReader(f)]


def fit_stage_stats(history: list[dict], smoothing: float = 1.0) -> dict[str, StageStats]:
    """Laplace-smoothed win rates per stage, split by whether the deal sat longer than winners usually do."""
    by_stage: dict[str, list[dict]] = defaultdict(list)
    for r in history:
        by_stage[r["stage"]].append(r)
    stats = {}
    for stage in STAGES:
        rows = by_stage.get(stage, [])
        won = [r for r in rows if r["won"]]
        threshold = percentile([r["days_in_stage"] for r in won], 0.75) if won else float("inf")
        fresh = [r for r in rows if r["days_in_stage"] <= threshold]
        stale = [r for r in rows if r["days_in_stage"] > threshold]

        def rate(group: list[dict]) -> float:
            return (sum(r["won"] for r in group) + smoothing) / (len(group) + 2 * smoothing)

        stats[stage] = StageStats(stage, rate(rows), rate(fresh), rate(stale), threshold, tuple(r["days_to_close"] for r in won))
    return stats


@dataclass(frozen=True)
class DealForecast:
    deal: Deal
    p_win: float
    p_in_quarter: float
    stale: bool

    @property
    def p_close(self) -> float:
        return self.p_win * self.p_in_quarter

    @property
    def expected(self) -> float:
        return self.deal.amount * self.p_close


def p_close_within(stats: StageStats, elapsed: int, days_left: int) -> float:
    """P(close within days_left | won, already elapsed days in stage), from the empirical cycle-time distribution."""
    still_open = [d for d in stats.won_days_to_close if d > elapsed]
    if len(still_open) < 5:
        return 0.5  # not enough evidence either way
    return sum(1 for d in still_open if d <= elapsed + days_left) / len(still_open)


def score_deal(deal: Deal, stats: dict[str, StageStats], days_left: int) -> DealForecast:
    s = stats[deal.stage]
    stale = deal.days_in_stage > s.stale_after_days
    p_win = s.win_rate_stale if stale else s.win_rate_fresh
    return DealForecast(deal, p_win, p_close_within(s, deal.days_in_stage, days_left), stale)


@dataclass(frozen=True)
class Forecast:
    rep_commit: float
    naive_weighted: float  # stage win rate x amount, no aging or timing
    weighted: float  # with aging and in-quarter timing
    p10: float
    p50: float
    p90: float
    p_hit_target: float
    deals: tuple[DealForecast, ...]


def monte_carlo(deals: list[DealForecast], target: float, sims: int = 10_000, seed: int = 42) -> tuple[list[float], float]:
    """Simulate each deal as an independent close/no-close draw; won deals close with a small discount haircut."""
    rng = random.Random(seed)
    totals = []
    for _ in range(sims):
        total = 0.0
        for f in deals:
            if rng.random() < f.p_close:
                total += f.deal.amount * rng.triangular(0.85, 1.0, 1.0)  # end-of-quarter discounting
        totals.append(total)
    return totals, sum(t >= target for t in totals) / sims


def forecast(pipeline: list[Deal], stats: dict[str, StageStats], days_left: int, target: float, sims: int = 10_000) -> Forecast:
    scored = [score_deal(d, stats, days_left) for d in pipeline]
    totals, p_hit = monte_carlo(scored, target, sims)
    return Forecast(
        rep_commit=sum(d.amount for d in pipeline if d.rep_category == "commit"),
        naive_weighted=sum(d.amount * stats[d.stage].win_rate for d in pipeline),
        weighted=sum(f.expected for f in scored),
        p10=percentile(totals, 0.10),
        p50=percentile(totals, 0.50),
        p90=percentile(totals, 0.90),
        p_hit_target=p_hit,
        deals=tuple(scored),
    )


def at_risk_commits(fc: Forecast) -> list[DealForecast]:
    """Deals the rep called commit that the model thinks are unlikely to land this quarter."""
    risky = [f for f in fc.deals if f.deal.rep_category == "commit" and (f.stale or f.p_close < 0.5)]
    return sorted(risky, key=lambda f: -f.deal.amount * (1 - f.p_close))
