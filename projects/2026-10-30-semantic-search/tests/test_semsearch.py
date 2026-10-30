import json
from pathlib import Path

import pytest

from semsearch import (BM25, HashingEmbedder, SearchEngine, VectorIndex, char_ngrams, cosine, evaluate, load_docs,
                       rrf, tokens)

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def engine():
    return SearchEngine(load_docs(DATA / "docs.jsonl"))


def test_tokens_drop_stopwords_and_keep_codes():
    assert tokens("How do I fix error E4012 on the VPN?") == ["fix", "error", "e4012", "vpn"]
    assert char_ngrams("pass", 3, 3) == ["<pa", "pas", "ass", "ss>"]


def test_embeddings_are_unit_length_deterministic_and_typo_tolerant():
    e = HashingEmbedder(256).fit(["reset your password", "book a meeting room", "printer is offline"])
    v = e.embed("password reset")
    assert sum(x * x for x in v) == pytest.approx(1.0)
    assert v == HashingEmbedder(256).fit(["reset your password", "book a meeting room", "printer is offline"]).embed(
        "password reset")
    assert cosine(e.embed("passwrd"), e.embed("password")) > cosine(e.embed("passwrd"), e.embed("printer"))
    assert e.embed("") == [0.0] * 256


def test_bm25_prefers_rare_terms_and_shorter_docs():
    bm = BM25().fit([("a", "vpn error e4012 certificate"), ("b", "vpn client vpn profile setup guide for the team"),
                     ("c", "printer offline")])
    assert bm.search("e4012")[0][0] == "a"
    assert bm.idf("e4012") > bm.idf("vpn")
    assert bm.search("nothing matches") == []


def test_rrf_rewards_agreement_between_rankers():
    fused = rrf([["a", "b", "c"], ["b", "a", "d"]], k=60)
    assert {fused[0][0], fused[1][0]} == {"a", "b"}
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)
    assert [d for d, _ in fused][-1] in {"c", "d"}


def test_index_rejects_bad_input_and_exact_search_ranks_by_cosine():
    idx = VectorIndex(2, nlist=2, nprobe=1)
    idx.add("x", [1.0, 0.0])
    idx.add("y", [0.0, 1.0])
    with pytest.raises(ValueError, match="duplicate"):
        idx.add("x", [1.0, 0.0])
    with pytest.raises(ValueError, match="dim"):
        idx.add("z", [1.0])
    assert [d for d, _ in idx.search([0.9, 0.1], 2)] == ["x", "y"]
    assert idx.search_ivf([0.9, 0.1], 2) == [("x", pytest.approx(0.9939, abs=1e-4))]  # probes x's cluster only


def test_ivf_scores_fewer_docs_but_matches_exact_top_hit(engine):
    queries = json.loads((DATA / "queries.json").read_text())
    agree, scored = 0, 0
    for q in queries:
        v = engine.embedder.embed(q["q"])
        scored += len(engine.index.candidates(v))
        hit = engine.index.search_ivf(v, 1)
        agree += bool(hit) and hit[0][0] == engine.index.search(v, 1)[0][0]
    assert scored / len(queries) < len(engine.index) * 0.6  # real work saved
    assert agree / len(queries) >= 0.8


def test_each_retriever_wins_where_expected(engine):
    top = lambda q, mode: engine.search(q, mode, 1)[0][0]
    assert top("E4012", "bm25") == "kb-002"  # exact code
    assert top("unlocking my acount", "dense") == "kb-026"  # misspelling + inflection
    assert engine.search("unlocking my acount", "bm25") == []
    assert top("unlocking my acount", "hybrid") == "kb-026"


def test_hybrid_beats_or_ties_both_retrievers_on_the_labelled_set(engine):
    queries = json.loads((DATA / "queries.json").read_text())
    res = {m: evaluate(engine, queries, m, 3) for m in ("bm25", "dense", "hybrid")}
    assert res["hybrid"]["mrr"] >= max(res["bm25"]["mrr"], res["dense"]["mrr"])
    assert res["hybrid"]["recall@3"] >= res["bm25"]["recall@3"]
    with pytest.raises(ValueError):
        engine.search("x", "magic")
