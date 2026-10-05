import math
from pathlib import Path

import pytest

from ab_test import (Experiment, achieved_power, analyze, chi2_sf, load_experiments, norm_cdf, norm_ppf,
                     sample_size_per_arm, srm_check, two_proportion_ztest)

DATA = Path(__file__).resolve().parent.parent / "data" / "experiments.json"


@pytest.mark.parametrize("p", [0.001, 0.5, 0.975])
def test_norm_ppf_inverts_cdf(p):
    assert norm_cdf(norm_ppf(p)) == pytest.approx(p, abs=1e-9)


def test_chi2_sf_matches_known_values():
    assert chi2_sf(3.841459, 1) == pytest.approx(0.05, abs=1e-6)
    assert chi2_sf(5.991465, 2) == pytest.approx(0.05, abs=1e-6)
    # df=1 chi-square is a squared normal
    assert chi2_sf(4.0, 1) == pytest.approx(2 * (1 - norm_cdf(2.0)), abs=1e-9)


def test_ztest_on_a_textbook_example():
    # 200/1000 vs 250/1000: pooled p=0.225, z = 0.05 / sqrt(0.225*0.775*0.002) = 2.6774
    r = two_proportion_ztest(200, 1000, 250, 1000)
    assert r.z == pytest.approx(2.6774, abs=1e-3)
    assert r.p_value == pytest.approx(0.00742, abs=1e-4)
    assert r.ci_low < 0.05 < r.ci_high
    assert r.rel_lift == pytest.approx(0.25)


def test_identical_arms_give_no_signal():
    r = two_proportion_ztest(100, 1000, 100, 1000)
    assert r.z == 0 and r.p_value == pytest.approx(1.0)


def test_sample_size_matches_standard_calculators():
    # Baseline 10%, +20% relative (10% -> 12%), alpha .05, power .8: ~3,841 per arm (Evan Miller / G*Power)
    assert sample_size_per_arm(0.10, 0.20) == pytest.approx(3841, abs=5)


def test_power_and_sample_size_are_consistent():
    n = sample_size_per_arm(0.04, 0.10, power=0.8)
    assert achieved_power(0.04, 0.10, n) == pytest.approx(0.8, abs=0.01)
    assert achieved_power(0.04, 0.10, n // 4) < 0.35


def test_srm_detects_a_skewed_split_and_passes_a_fair_one():
    _, p_fair = srm_check([50_100, 49_900], [0.5, 0.5])
    _, p_bad = srm_check([51_000, 49_000], [0.5, 0.5])
    assert p_fair > 0.5
    assert p_bad < 1e-9
    with pytest.raises(ValueError):
        srm_check([10, 10], [0.6, 0.6])


def exp(control, treatment, mde=0.05, split=(0.5, 0.5), guardrail=None):
    return Experiment("t", "h", split, mde, control, treatment, guardrail)


def test_srm_overrides_an_apparent_win():
    v = analyze(exp((20_000, 600), (18_500, 700)))
    assert v.decision == "INVESTIGATE SRM"


def test_small_test_with_no_signal_keeps_running():
    v = analyze(exp((1_000, 100), (1_000, 108)))
    assert v.decision == "KEEP RUNNING" and v.power < 0.8


def test_significant_drop_is_dont_ship():
    assert analyze(exp((50_000, 5_000), (50_000, 4_600))).decision == "DON'T SHIP"


def test_guardrail_blocks_a_winning_variant():
    g = {"metric": "returns", "control": (5_000, 250), "treatment": (5_600, 420), "max_rel_increase": 0.1}
    v = analyze(exp((50_000, 5_000), (50_000, 5_600), guardrail=g))
    assert v.decision == "DON'T SHIP"
    assert any("guardrail returns worsened" in r for r in v.reasons)


def test_sample_portfolio_decisions():
    decisions = {e.name: analyze(e).decision for e in load_experiments(DATA)}
    assert decisions == {
        "checkout-express-pay": "SHIP",
        "onboarding-checklist": "KEEP RUNNING",
        "pricing-annual-default": "INVESTIGATE SRM",
        "search-autocomplete-v2": "DON'T SHIP",
        "free-shipping-banner": "DON'T SHIP",
    }
    assert not any(math.isnan(analyze(e).test.z) for e in load_experiments(DATA))
