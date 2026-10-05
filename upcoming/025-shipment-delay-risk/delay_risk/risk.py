"""Turn shipment-level scores into lane x carrier risk and actions for next week's plan."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from .features import featurize
from .stumps import StumpEnsemble

HIGH, WATCH = 0.5, 0.3


def tier(p: float) -> str:
    return "HIGH" if p >= HIGH else "watch" if p >= WATCH else "ok"


def baseline_rates(rows: list[dict], key: str) -> dict[str, float]:
    """Historic delay rate per carrier or lane: the baseline a planner already has in their head."""
    counts: dict[str, list[int]] = {}
    for r in rows:
        counts.setdefault(r[key], []).append(int(r["delayed"]))
    return {k: sum(v) / len(v) for k, v in counts.items()}


def lane_carrier_matrix(model: StumpEnsemble, rows: list[dict]) -> dict[str, dict[str, float]]:
    """Predicted risk for a typical load on each lane with each carrier, under median conditions.

    Holding weather, day and season fixed isolates the lane x carrier effect, which is what you
    negotiate in a carrier award; the raw delay rate mixes it with when each carrier happened to run.
    """
    weather = median(float(r["weather_index"]) for r in rows)
    otp = {c: median(float(r["carrier_otp_90d"]) for r in rows if r["carrier"] == c) for c in {r["carrier"] for r in rows}}
    out: dict[str, dict[str, float]] = {}
    for lane in sorted({r["lane"] for r in rows}):
        on_lane = [r for r in rows if r["lane"] == lane]
        planned = median(int(r["planned_days"]) for r in on_lane if r["mode"] == "FTL") if any(
            r["mode"] == "FTL" for r in on_lane) else median(int(r["planned_days"]) for r in on_lane)
        for carrier in sorted(otp):
            typical = {"lane": lane, "carrier": carrier, "mode": "FTL", "distance_km": on_lane[0]["distance_km"],
                       "planned_days": planned, "ship_dow": "Tue", "peak_season": 0, "weather_index": weather,
                       "carrier_otp_90d": otp[carrier]}
            out.setdefault(lane, {})[carrier] = model.predict_proba(featurize(typical))
    return out


@dataclass
class PlanRisk:
    shipment_id: str
    lane: str
    carrier: str
    risk: float
    tier: str
    reasons: list[str]
    swap: tuple[str, float] | None  # (carrier, risk) if another carrier is materially safer


def score_plan(model: StumpEnsemble, plan: list[dict], carriers: list[str], otp: dict[str, float],
               min_gain: float = 0.10) -> list[PlanRisk]:
    out = []
    for row in plan:
        x = featurize(row)
        p = model.predict_proba(x)
        swap = None
        if p >= WATCH:
            alts = []
            for c in carriers:
                if c != row["carrier"]:
                    alt = dict(row, carrier=c, carrier_otp_90d=otp[c])
                    alts.append((model.predict_proba(featurize(alt)), c))
            best_p, best_c = min(alts)
            if p - best_p >= min_gain:
                swap = (best_c, best_p)
        out.append(PlanRisk(row["shipment_id"], row["lane"], row["carrier"], p, tier(p), model.reasons(x), swap))
    return sorted(out, key=lambda r: -r.risk)
