"""Composite supplier risk index: financial, geographic and delivery sub-scores (0 = safe, 100 = critical)."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

WEIGHTS = {"financial": 0.35, "geo": 0.30, "delivery": 0.35}


@dataclass(frozen=True)
class Supplier:
    name: str
    category: str
    country: str
    annual_spend: float
    single_source: bool
    current_ratio: float
    debt_to_equity: float
    net_margin_pct: float
    days_payable_trend: float  # +days: they are stretching payments to their own suppliers
    on_time_pct: float
    lead_time_days: float
    lead_time_cv: float
    defect_ppm: float


@dataclass(frozen=True)
class Country:
    political_risk: float
    logistics_risk: float
    natural_hazard: float


def load_suppliers(path: Path) -> list[Supplier]:
    with open(path, newline="") as f:
        return [Supplier(r["supplier"], r["category"], r["country"], float(r["annual_spend_usd"]),
                         r["single_source"] == "yes", float(r["current_ratio"]), float(r["debt_to_equity"]),
                         float(r["net_margin_pct"]), float(r["days_payable_trend"]), float(r["on_time_pct"]),
                         float(r["lead_time_days"]), float(r["lead_time_cv"]), float(r["defect_ppm"]))
                for r in csv.DictReader(f)]


def load_countries(path: Path) -> dict[str, Country]:
    with open(path, newline="") as f:
        return {r["country"]: Country(float(r["political_risk"]), float(r["logistics_risk"]), float(r["natural_hazard"]))
                for r in csv.DictReader(f)}


def ramp(x: float, good: float, bad: float) -> float:
    """Linear 0..100 risk between a 'good' and a 'bad' anchor (works in either direction)."""
    t = (x - good) / (bad - good)
    return 100 * min(1.0, max(0.0, t))


def financial_score(s: Supplier) -> float:
    parts = [
        (0.30, ramp(s.current_ratio, 2.0, 0.8)),
        (0.25, ramp(s.debt_to_equity, 0.5, 2.5)),
        (0.25, ramp(s.net_margin_pct, 10.0, -5.0)),
        (0.20, ramp(s.days_payable_trend, 0.0, 30.0)),  # stretching payables is an early distress signal
    ]
    return sum(w * v for w, v in parts)


def geo_score(c: Country) -> float:
    return 0.4 * c.political_risk + 0.35 * c.logistics_risk + 0.25 * c.natural_hazard


def delivery_score(s: Supplier) -> float:
    parts = [
        (0.35, ramp(s.on_time_pct, 98.0, 80.0)),
        (0.25, ramp(s.lead_time_cv, 0.05, 0.45)),
        (0.20, ramp(s.lead_time_days, 7.0, 60.0)),
        (0.20, ramp(s.defect_ppm, 50.0, 1500.0)),
    ]
    return sum(w * v for w, v in parts)


@dataclass
class RiskResult:
    supplier: Supplier
    financial: float
    geo: float
    delivery: float
    composite: float
    disruption_prob: float  # annualized probability of a material disruption
    exposure_usd: float  # expected annual cost of disruption

    @property
    def tier(self) -> str:
        return "critical" if self.composite >= 55 else "high" if self.composite >= 40 else "medium" if self.composite >= 25 else "low"


def disruption_probability(composite: float) -> float:
    """Logistic map calibrated so a score of 25 -> 3% and 60 -> 25% per year (illustrative;
    recalibrate against your own disruption history)."""
    return 1 / (1 + math.exp(-(composite - 76.2) / 14.7))


def score(s: Supplier, countries: dict[str, Country], impact_multiplier: float = 1.5) -> RiskResult:
    """Exposure = P(disruption) x spend x impact multiplier (lost margin, expediting, line stoppage).
    Single-source parts double the multiplier because there is no quick alternative."""
    f, g, d = financial_score(s), geo_score(countries[s.country]), delivery_score(s)
    comp = WEIGHTS["financial"] * f + WEIGHTS["geo"] * g + WEIGHTS["delivery"] * d
    p = disruption_probability(comp)
    mult = impact_multiplier * (2 if s.single_source else 1)
    return RiskResult(s, f, g, d, comp, p, p * s.annual_spend * mult)


def score_all(suppliers: list[Supplier], countries: dict[str, Country]) -> list[RiskResult]:
    return sorted((score(s, countries) for s in suppliers), key=lambda r: -r.exposure_usd)


def concentration(suppliers: list[Supplier]) -> dict[str, float]:
    """Share of spend by country, and the Herfindahl index (0-1) across countries."""
    total = sum(s.annual_spend for s in suppliers)
    shares: dict[str, float] = {}
    for s in suppliers:
        shares[s.country] = shares.get(s.country, 0) + s.annual_spend / total
    shares["HHI"] = sum(v * v for v in shares.values())
    return shares


