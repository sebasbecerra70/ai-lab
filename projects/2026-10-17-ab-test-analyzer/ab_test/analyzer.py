"""Turns raw experiment counts into a ship / don't-ship / keep-running recommendation."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .stats import ZTestResult, achieved_power, srm_check, two_proportion_ztest

SRM_ALPHA = 0.001  # strict on purpose: SRM is checked on every experiment, so false alarms add up


@dataclass(frozen=True)
class Experiment:
    name: str
    hypothesis: str
    split: tuple[float, float]
    mde_rel: float  # smallest relative lift worth shipping, agreed before launch
    control: tuple[int, int]  # (visitors, conversions)
    treatment: tuple[int, int]
    guardrail: dict | None = None  # {"metric", "control": (n, events), "treatment": (n, events), "max_rel_increase"}


@dataclass
class Verdict:
    experiment: Experiment
    decision: str  # SHIP, DON'T SHIP, KEEP RUNNING, INVESTIGATE SRM
    reasons: list[str] = field(default_factory=list)
    test: ZTestResult | None = None
    srm_p: float = 1.0
    power: float = 0.0


def load_experiments(path: Path) -> list[Experiment]:
    raw = json.loads(Path(path).read_text())
    return [
        Experiment(e["name"], e["hypothesis"], tuple(e["split"]), e["mde_rel"], tuple(e["control"]), tuple(e["treatment"]), e.get("guardrail"))
        for e in raw
    ]


def analyze(exp: Experiment, alpha: float = 0.05) -> Verdict:
    (n_a, c_a), (n_b, c_b) = exp.control, exp.treatment
    _, srm_p = srm_check([n_a, n_b], list(exp.split))
    if srm_p < SRM_ALPHA:
        expected = (n_a + n_b) * exp.split[1]
        return Verdict(exp, "INVESTIGATE SRM", [
            f"sample ratio mismatch: treatment got {n_b:,} visitors vs {expected:,.0f} expected (p={srm_p:.1e})",
            "assignment or logging is broken; the lift below cannot be trusted",
        ], two_proportion_ztest(c_a, n_a, c_b, n_b, alpha), srm_p)

    t = two_proportion_ztest(c_a, n_a, c_b, n_b, alpha)
    power = achieved_power(t.p_control, exp.mde_rel, min(n_a, n_b), alpha)
    v = Verdict(exp, "", test=t, srm_p=srm_p, power=power)
    mde_abs = t.p_control * exp.mde_rel
    if t.p_value < alpha and t.abs_lift > 0:
        v.decision = "SHIP"
        v.reasons.append(f"significant lift {t.rel_lift:+.1%} (p={t.p_value:.4f})")
        if t.ci_low < mde_abs:
            v.reasons.append(f"CI lower bound {t.ci_low * 100:+.2f}pp is below the {mde_abs * 100:+.2f}pp MDE: real, but maybe smaller than planned")
    elif t.p_value < alpha:
        v.decision = "DON'T SHIP"
        v.reasons.append(f"significant drop {t.rel_lift:+.1%} (p={t.p_value:.4f})")
    elif power < 0.8:
        v.decision = "KEEP RUNNING"
        v.reasons.append(f"not significant (p={t.p_value:.2f}) and only {power:.0%} power for a {exp.mde_rel:.0%} lift")
    else:
        v.decision = "DON'T SHIP"
        bound = "rules out" if t.ci_high < mde_abs else "does not rule out"
        v.reasons.append(f"well powered ({power:.0%}) and no significant effect; CI upper bound {t.ci_high * 100:+.2f}pp {bound} the {mde_abs * 100:+.2f}pp MDE")

    if exp.guardrail and v.decision == "SHIP":
        g = exp.guardrail
        gt = two_proportion_ztest(g["control"][1], g["control"][0], g["treatment"][1], g["treatment"][0], alpha)
        if gt.p_value < alpha and gt.rel_lift > g["max_rel_increase"]:
            v.decision = "DON'T SHIP"
            v.reasons.append(f"guardrail {g['metric']} worsened {gt.rel_lift:+.1%} (p={gt.p_value:.4f}), over the {g['max_rel_increase']:.0%} limit")
        else:
            v.reasons.append(f"guardrail {g['metric']} ok ({gt.rel_lift:+.1%}, p={gt.p_value:.2f})")
    return v
