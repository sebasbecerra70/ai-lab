from pathlib import Path

import pytest

from partner_fit import (Partner, ahp_weights, explain, load_config, load_partners, normalize,
                         pairwise_matrix, principal_eigenvector, score, sensitivity)

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def setup():
    directions, ahp = load_config(DATA / "criteria.json")
    return directions, ahp, load_partners(DATA / "partners.csv", list(directions))


def test_pairwise_matrix_is_reciprocal():
    m = pairwise_matrix(["a", "b", "c"], [("a", "b", 3), ("a", "c", 5), ("b", "c", 2)])
    assert m[1][0] == pytest.approx(1 / 3) and m[2][2] == 1.0


def test_missing_comparison_is_rejected():
    with pytest.raises(ValueError, match="missing"):
        pairwise_matrix(["a", "b", "c"], [("a", "b", 3)])


def test_perfectly_consistent_matrix_recovers_known_weights():
    # true weights 0.6, 0.3, 0.1 -> ratios 2, 6, 3
    res = ahp_weights(["a", "b", "c"], [("a", "b", 2), ("a", "c", 6), ("b", "c", 3)])
    assert [round(res.weights[k], 3) for k in "abc"] == [0.6, 0.3, 0.1]
    assert res.consistency_ratio == pytest.approx(0.0, abs=1e-9)


def test_inconsistent_judgments_fail_the_ratio():
    # a>b, b>c, but c>>a: circular preferences
    res = ahp_weights(["a", "b", "c"], [("a", "b", 5), ("b", "c", 5), ("a", "c", 1 / 5)])
    assert not res.consistent and res.consistency_ratio > 0.1


def test_eigenvector_sums_to_one_and_lambda_ge_n():
    w, lam = principal_eigenvector([[1, 3], [1 / 3, 1]])
    assert sum(w) == pytest.approx(1.0) and lam == pytest.approx(2.0)


def test_sample_config_weights_are_consistent(setup):
    _, ahp, _ = setup
    assert ahp.consistent
    assert sum(ahp.weights.values()) == pytest.approx(1.0)
    assert max(ahp.weights, key=ahp.weights.get) in {"revenue_potential", "strategic_alignment"}


def test_cost_criteria_are_inverted():
    ps = [Partner("x", "", {"effort": 2}), Partner("y", "", {"effort": 10})]
    norm = normalize(ps, {"effort": "cost"})
    assert norm["x"]["effort"] == 1.0 and norm["y"]["effort"] == 0.0


def test_scores_are_bounded_and_contributions_add_up(setup):
    directions, ahp, partners = setup
    ranked = score(partners, directions, ahp.weights)
    assert all(0 <= s.score <= 100 for s in ranked)
    assert all(sum(s.contributions.values()) == pytest.approx(s.score) for s in ranked)
    assert ranked[0].partner.name == "Atlas ERP"
    assert "weakest on integration_effort" in explain(ranked[0])


def test_dominated_partner_ranks_last():
    d = {"rev": "benefit", "effort": "cost"}
    ps = [Partner("good", "", {"rev": 9, "effort": 1}), Partner("bad", "", {"rev": 1, "effort": 9}),
          Partner("mid", "", {"rev": 5, "effort": 5})]
    assert [s.partner.name for s in score(ps, d, {"rev": 0.5, "effort": 0.5})] == ["good", "mid", "bad"]


def test_sensitivity_detects_leader_flip(setup):
    directions, ahp, partners = setup
    rows = sensitivity(partners, directions, ahp.weights)
    assert len(rows) == 4 * len(directions)
    flips = {(r.criterion, r.change) for r in rows if r.leader_changed}
    assert ("revenue_potential", -0.5) in flips
    assert ("financial_health", 0.25) not in flips
