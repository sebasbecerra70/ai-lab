from pathlib import Path

import pytest

from ticket_routing import TRIAGE, CentroidRouter, TfIdf, cosine, keyword_route, load, metrics, sweep, tokens
from ticket_routing.synth import generate

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def train():
    return load(DATA / "train.csv")


@pytest.fixture(scope="module")
def test_rows():
    return load(DATA / "test.csv")


@pytest.fixture(scope="module")
def router(train):
    return CentroidRouter().fit([r["text"] for r in train], [r["queue"] for r in train])


def test_tokens_drop_filler_and_add_bigrams():
    assert tokens("Hi team, VPN keeps dropping asap") == ["vpn", "keeps", "dropping", "vpn keeps", "keeps dropping"]


def test_tfidf_vectors_are_unit_length_and_rare_terms_weigh_more():
    vec = TfIdf(min_df=1).fit(["wifi down", "wifi slow", "wifi down phishing"])
    v = vec.transform("wifi phishing")
    assert sum(x * x for x in v.values()) == pytest.approx(1.0)
    assert v["phishing"] > v["wifi"]
    assert cosine(v, v) == pytest.approx(1.0)


def test_min_df_drops_one_off_terms():
    vec = TfIdf(min_df=2).fit(["printer jammed", "printer offline", "zebra"])
    assert "printer" in vec.idf and "zebra" not in vec.idf
    assert vec.transform("zebra") == {}


@pytest.mark.parametrize("text,queue", [
    ("wifi keeps dropping on the 2nd floor", "network"),
    ("locked out of my account after vacation", "access"),
    ("monitor will not turn on", "hardware"),
    ("Excel crashes when I open attachments", "software"),
    ("got a suspicious email asking for my password", "security"),
])
def test_routes_clear_tickets(router, text, queue):
    assert router.route(text).queue == queue


def test_gibberish_and_empty_go_to_triage(router):
    assert router.route("lorem ipsum dolor").queue == TRIAGE
    r = router.route("")
    assert r.fell_back and r.reason == "no queue is similar enough"


def test_close_calls_fall_back_on_margin(router):
    strict = CentroidRouter(min_score=0.0, min_margin=0.99)
    strict.vec, strict.centroids = router.vec, router.centroids
    r = strict.route("VPN says my account is not authorized")
    assert r.queue == TRIAGE and r.best == "access" and "too close" in r.reason


def test_metrics_definitions():
    m = metrics(["network", "triage", "access", "triage", "hardware"],
                ["network", "network", "network", "triage", "triage"])
    assert m.auto_rate == pytest.approx(2 / 3)
    assert m.routed_accuracy == 0.5 and m.misroutes == 1
    assert m.end_to_end == pytest.approx(1 / 3)
    assert m.off_topic_caught == 0.5


def test_centroid_beats_keyword_rules_on_held_out_phrasings(router, test_rows):
    truth = [r["queue"] for r in test_rows]
    kw = metrics([keyword_route(r["text"]) for r in test_rows], truth)
    tf = metrics([router.route(r["text"]).queue for r in test_rows], truth)
    assert tf.end_to_end > kw.end_to_end + 0.1
    assert tf.misroutes <= kw.misroutes
    assert tf.routed_accuracy >= 0.95


def test_raising_the_threshold_trades_coverage_for_safety(router, test_rows):
    rows = sweep(router, test_rows, [0.0, 0.12, 0.30])
    autos = [m.auto_rate for _, m in rows]
    assert autos == sorted(autos, reverse=True)
    assert rows[-1][1].misroutes == 0
    assert router.min_score == 0.12  # sweep restores the live threshold


def test_explain_returns_matching_terms(router):
    terms = router.explain("clicked a link in a phishing email", "security", k=5)
    assert "phishing" in terms and len(terms) <= 5


def test_synthetic_data_is_reproducible():
    assert generate(3, seed=9) == generate(3, seed=9)
    assert sum(r["queue"] == "triage" for r in generate(1, seed=9, off_topic=4)) == 4
