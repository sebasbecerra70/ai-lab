"""Rolling-origin backtest and error metrics (MAPE, WAPE, bias)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .models import Forecaster


def mape(actual: list[float], forecast: list[float]) -> float | None:
    """Mean absolute % error over non-zero actuals. Undefined (None) when every actual is zero."""
    pairs = [(a, f) for a, f in zip(actual, forecast) if a != 0]
    if not pairs:
        return None
    return sum(abs(a - f) / abs(a) for a, f in pairs) / len(pairs)


def wape(actual: list[float], forecast: list[float]) -> float:
    """Sum |error| / sum |actual|. Volume-weighted, and well-defined for intermittent demand."""
    denom = sum(abs(a) for a in actual)
    return sum(abs(a - f) for a, f in zip(actual, forecast)) / denom if denom else 0.0


def bias(actual: list[float], forecast: list[float]) -> float:
    """Positive = over-forecasting (excess stock); negative = under-forecasting (stockouts)."""
    denom = sum(abs(a) for a in actual)
    return sum(f - a for a, f in zip(actual, forecast)) / denom if denom else 0.0


def wape_totals(actual: list[float], forecast: list[float], horizon: int) -> float:
    """WAPE on per-origin horizon totals. For spare parts, what matters is total demand over the lead
    time (does the shelf cover it?), not which exact week the single unit is ordered."""
    a = [sum(actual[i:i + horizon]) for i in range(0, len(actual), horizon)]
    f = [sum(forecast[i:i + horizon]) for i in range(0, len(forecast), horizon)]
    return wape(a, f)


@dataclass
class Score:
    model: str
    mape: float | None
    wape: float
    bias: float
    wape_horizon: float


def backtest(series: list[float], model: Forecaster, horizon: int = 4, origins: int = 20) -> tuple[list[float], list[float]]:
    """Forecast from `origins` cut points, each `horizon` weeks apart, stopping at the end of the series.

    Rolling origins average over several cut points, so one lucky or unlucky week doesn't pick the model.
    """
    first = len(series) - horizon * origins
    if first < 1:
        raise ValueError("series too short for this many origins")
    actual, predicted = [], []
    for origin in range(first, len(series) - horizon + 1, horizon):
        actual += series[origin:origin + horizon]
        predicted += model(series[:origin], horizon)
    return actual, predicted


def evaluate(series: list[float], models: dict[str, Forecaster], horizon: int = 4, origins: int = 20) -> list[Score]:
    """Score every model; rank by weekly WAPE for smooth demand, by horizon-total WAPE for intermittent."""
    scores = []
    for name, model in models.items():
        a, p = backtest(series, model, horizon, origins)
        scores.append(Score(name, mape(a, p), wape(a, p), bias(a, p), wape_totals(a, p, horizon)))
    key = (lambda s: s.wape_horizon) if intermittency(series) > 1.32 else (lambda s: s.wape)
    return sorted(scores, key=key)


def intermittency(series: list[float]) -> float:
    """Average demand interval (ADI): mean periods between non-zero demands. ADI > 1.32 = intermittent."""
    nz = [i for i, v in enumerate(series) if v > 0]
    if len(nz) < 2:
        return float("inf")
    return (nz[-1] - nz[0]) / (len(nz) - 1)


def load_series(path: str | Path) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out.setdefault(row["sku"], []).append(float(row["units"]))
    return out
