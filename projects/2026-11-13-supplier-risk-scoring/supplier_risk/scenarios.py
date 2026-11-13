"""What-if stress tests: apply shocks to countries or suppliers and re-score."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from .scoring import Country, RiskResult, Supplier, score_all


@dataclass
class Scenario:
    name: str
    description: str
    country_shock: dict
    lead_time_multiplier: dict
    supplier_shock: dict


def load_scenarios(path: Path) -> list[Scenario]:
    return [Scenario(d["name"], d.get("description", ""), d.get("country_shock", {}),
                     d.get("lead_time_multiplier", {}), d.get("supplier_shock", {}))
            for d in json.loads(Path(path).read_text())]


def apply(sc: Scenario, suppliers: list[Supplier], countries: dict[str, Country]):
    new_countries = dict(countries)
    for code, deltas in sc.country_shock.items():
        c = new_countries[code]
        new_countries[code] = replace(c, **{k: min(100.0, getattr(c, k) + v) for k, v in deltas.items()})
    new_suppliers = []
    for s in suppliers:
        if s.country in sc.lead_time_multiplier:
            m = sc.lead_time_multiplier[s.country]
            s = replace(s, lead_time_days=s.lead_time_days * m, lead_time_cv=s.lead_time_cv * m,
                        on_time_pct=max(0.0, s.on_time_pct - 25 * (m - 1)))  # 1.4x -> -10 pts
        if s.name in sc.supplier_shock:
            s = replace(s, **sc.supplier_shock[s.name])
        new_suppliers.append(s)
    return new_suppliers, new_countries


@dataclass
class ScenarioImpact:
    scenario: Scenario
    total_exposure_before: float
    total_exposure_after: float
    tier_changes: list[tuple[str, str, str]]  # supplier, before, after
    top_movers: list[tuple[str, float]]  # supplier, exposure delta


def run(sc: Scenario, suppliers: list[Supplier], countries: dict[str, Country]) -> ScenarioImpact:
    before = {r.supplier.name: r for r in score_all(suppliers, countries)}
    after_list: list[RiskResult] = score_all(*apply(sc, suppliers, countries))
    after = {r.supplier.name: r for r in after_list}
    changes = [(n, before[n].tier, after[n].tier) for n in before if before[n].tier != after[n].tier]
    movers = sorted(((n, after[n].exposure_usd - before[n].exposure_usd) for n in before), key=lambda x: -x[1])
    return ScenarioImpact(sc, sum(r.exposure_usd for r in before.values()),
                          sum(r.exposure_usd for r in after.values()), changes, movers[:3])
