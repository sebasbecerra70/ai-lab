from pathlib import Path

import pytest

from model_router import LARGE, SMALL, DifficultyClassifier, MockLLM, Router, evaluate, frontier, load_jsonl
from model_router.features import FEATURE_NAMES, extract
from model_router.router import accuracy, estimate_tokens

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def trained():
    texts, labels = load_jsonl(DATA / "prompts.jsonl")
    return DifficultyClassifier().fit(texts, labels), texts, labels


def test_feature_vector_shape_and_signals():
    easy, hard = extract("What is 2+2?"), extract("Design and explain step by step a Python function")
    assert len(easy) == len(FEATURE_NAMES)
    assert hard[1] >= 2 and hard[2] == 1 and hard[3] >= 1
    assert easy[-1] == 1.0


def test_classifier_fits_training_data(trained):
    clf, texts, labels = trained
    assert accuracy(clf, texts, labels) >= 0.9


def test_classifier_generalizes_to_holdout(trained):
    clf, _, _ = trained
    texts, labels = load_jsonl(DATA / "holdout.jsonl")
    assert accuracy(clf, texts, labels) >= 0.8


def test_probability_ordering(trained):
    clf, _, _ = trained
    assert clf.predict_proba("Prove the theorem step by step and analyze edge cases.") > \
        clf.predict_proba("What is the capital of Spain?")


def test_router_threshold_extremes(trained):
    clf, _, _ = trained
    assert Router(clf, threshold=0.0).decide("hi").tier is LARGE
    assert Router(clf, threshold=1.01).decide("Design a distributed system").tier is SMALL


def test_router_run_uses_selected_client(trained):
    clf, _, _ = trained
    clients = {"small": MockLLM("small"), "large": MockLLM("large")}
    d, out = Router(clf).run("Explain and compare three architectures step by step, with trade-offs.", clients)
    assert d.tier is LARGE and out.startswith("[large]")


def test_cost_math():
    assert SMALL.cost(1_000_000, 0) == pytest.approx(1.0)
    assert LARGE.cost(0, 1_000_000) == pytest.approx(10.0)
    assert estimate_tokens("a b c", hard=True)[1] > estimate_tokens("a b c", hard=False)[1]


def test_frontier_router_beats_always_large_on_cost(trained):
    clf, texts, labels = trained
    reports = {r.policy: r for r in frontier(clf, texts, labels)}
    small, large, router = reports["always-small"], reports["always-large"], reports["router@0.50"]
    assert small.cost_usd < router.cost_usd < large.cost_usd
    assert router.expected_quality > small.expected_quality
    assert router.expected_quality >= large.expected_quality - 0.03


def test_lower_threshold_trades_cost_for_quality(trained):
    clf, _, _ = trained
    texts, labels = load_jsonl(DATA / "holdout.jsonl")
    reports = {r.policy: r for r in frontier(clf, texts, labels)}
    lo, hi = reports["router@0.20"], reports["router@0.80"]
    assert lo.pct_large >= hi.pct_large and lo.expected_quality >= hi.expected_quality


def test_evaluate_counts_large_share():
    r = evaluate("x", lambda t: LARGE, ["a", "b"], [0, 1])
    assert r.pct_large == 1.0 and r.expected_quality == pytest.approx((0.97 + 0.93) / 2)
