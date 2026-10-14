"""Baseline forecasters. Each takes a history and a horizon and returns `horizon` point forecasts."""
from __future__ import annotations

import itertools
from typing import Callable

Forecaster = Callable[[list[float], int], list[float]]


def naive(history: list[float], h: int) -> list[float]:
    return [history[-1]] * h


def seasonal_naive(season: int = 52) -> Forecaster:
    def f(history: list[float], h: int) -> list[float]:
        if len(history) < season:
            return naive(history, h)
        return [history[-season + (i % season)] for i in range(h)]
    return f


def moving_average(window: int = 8) -> Forecaster:
    def f(history: list[float], h: int) -> list[float]:
        w = history[-window:]
        return [sum(w) / len(w)] * h
    return f


def holt_winters_fit(y: list[float], season: int, alpha: float, beta: float, gamma: float
                     ) -> tuple[float, float, list[float], float]:
    """Additive Holt-Winters. Returns (level, trend, seasonals, in-sample SSE of one-step errors)."""
    if len(y) < 2 * season:
        raise ValueError("Holt-Winters needs at least two full seasons of history")
    level = sum(y[:season]) / season
    trend = (sum(y[season:2 * season]) - sum(y[:season])) / season ** 2
    seasonals = [y[i] - level for i in range(season)]
    sse = 0.0
    for t in range(season, len(y)):
        s = seasonals[t % season]
        sse += (y[t] - (level + trend + s)) ** 2
        prev_level = level
        level = alpha * (y[t] - s) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        seasonals[t % season] = gamma * (y[t] - level) + (1 - gamma) * s
    return level, trend, seasonals, sse


def holt_winters(season: int = 52, grid: tuple[float, ...] = (0.1, 0.3, 0.5)) -> Forecaster:
    """Grid-search the smoothing parameters on in-sample one-step SSE. Small grid: robust and cheap."""
    def f(history: list[float], h: int) -> list[float]:
        if len(history) < 2 * season:
            return naive(history, h)
        best = None
        for a, b, g in itertools.product(grid, (0.01, 0.05), grid):
            fit = holt_winters_fit(history, season, a, b, g)
            if best is None or fit[3] < best[3]:
                best = fit
        level, trend, seasonals, _ = best
        n = len(history)
        return [max(0.0, level + (i + 1) * trend + seasonals[(n + i) % season]) for i in range(h)]
    return f


def croston(alpha: float = 0.1, sba: bool = True) -> Forecaster:
    """Croston's method for intermittent demand: smooth non-zero sizes and the gaps between them separately.

    The SBA (Syntetos-Boylan) correction (1 - alpha/2) removes Croston's known upward bias.
    """
    def f(history: list[float], h: int) -> list[float]:
        demands = [(i, v) for i, v in enumerate(history) if v > 0]
        if not demands:
            return [0.0] * h
        size, interval = demands[0][1], float(demands[0][0] + 1)
        last = demands[0][0]
        for i, v in demands[1:]:
            size = alpha * v + (1 - alpha) * size
            interval = alpha * (i - last) + (1 - alpha) * interval
            last = i
        rate = size / interval * ((1 - alpha / 2) if sba else 1.0)
        return [rate] * h
    return f


def default_models(season: int = 52) -> dict[str, Forecaster]:
    return {
        "naive": naive,
        "seasonal_naive": seasonal_naive(season),
        "moving_avg_8": moving_average(8),
        "holt_winters": holt_winters(season),
        "croston_sba": croston(),
    }
