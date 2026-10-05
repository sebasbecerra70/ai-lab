from pathlib import Path

import pytest

from okr_reporter import MockLLM, biggest_gap, check, classify, facts, progress, score, trend, write_update

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def scored():
    cfg, objectives, week = score(DATA / "okrs.json", DATA / "metrics.csv")
    return cfg, objectives, week


def kr(objectives, kr_id):
    return next(k for o in objectives for k in o.krs if k.id == kr_id)


def test_progress_handles_both_directions():
    assert progress(0.31, 0.40, 0.355) == pytest.approx(0.5)
    assert progress(640, 300, 470) == pytest.approx(0.5)   # lower is better
    assert progress(640, 300, 700) == 0.0                   # regressions clamp at zero
    assert progress(10, 10, 10) == 1.0


def test_trend_is_least_squares_slope_over_the_window():
    assert trend([1, 2, 3, 4, 5, 6]) == pytest.approx(1.0)
    assert trend([100, 0, 10, 20, 30], window=4) == pytest.approx(10.0)  # old outlier ignored
    assert trend([5]) == 0.0


def test_status_thresholds():
    assert classify(0.95, 0.5) == "on track"
    assert classify(0.75, 0.5) == "at risk"
    assert classify(0.40, 0.2) == "off track"
    assert classify(0.40, 1.0) == "done"


def test_sample_kr_math(scored):
    _, objectives, week = scored
    assert week == 8
    k = kr(objectives, "KR1.1")
    assert k.current == 0.357
    assert k.progress == pytest.approx((0.357 - 0.31) / 0.09)
    assert k.expected == pytest.approx(8 / 13)
    assert k.status == "at risk"
    assert kr(objectives, "KR2.1").status == "off track"
    assert kr(objectives, "KR3.1").status == "on track"


def test_objective_score_is_weighted_and_caps_overachievement(scored):
    _, objectives, _ = scored
    o3 = objectives[2]
    expected = sum(k.weight * min(k.progress, 1) for k in o3.krs) / sum(k.weight for k in o3.krs)
    assert o3.score == pytest.approx(expected)
    assert o3.projected <= 1.0


def test_biggest_gap_weighs_importance_and_shortfall(scored):
    _, objectives, _ = scored
    assert biggest_gap(objectives).id == "KR2.1"  # weight 0.5, projected ~19%


def test_facts_block_lists_every_kr(scored):
    _, objectives, week = scored
    f = facts(objectives, week, 13)
    assert sum(line.startswith("KR") for line in f.splitlines()) == 8
    assert "OVERALL: 4 of 8 KRs on track or done, 4 need attention" in f
    assert "BIGGEST GAP: KR2.1" in f


def test_mock_narrative_passes_fact_check(scored):
    _, objectives, week = scored
    text, chk = write_update(MockLLM(), objectives, week, 13)
    assert chk.ok
    assert "KR2.1" in text and "**Ask:**" in text


def test_fact_check_catches_invented_numbers_and_skipped_risks(scored):
    _, objectives, week = scored
    f = facts(objectives, week, 13)
    bad = "Great quarter! Activation hit 41.5% and NRR is fine. KR1.1 KR1.3 KR2.3 are moving."
    chk = check(bad, f, objectives)
    assert chk.unknown_numbers == ["41.5%"]
    assert chk.missing_krs == ["KR2.1"]
    assert not chk.ok
