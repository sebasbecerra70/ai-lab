from pathlib import Path

import pytest

from chunkbench import (BM25, Chunk, Doc, Question, contains_answer, evaluate, fixed, heading, load_docs,
                        load_questions, sections, sentence, sentences, tokenize)
from chunkbench.chunkers import plain

ROOT = Path(__file__).resolve().parent.parent
MD = Doc("t.md", "# Policy\n\nIntro line here.\n\n## Travel\n\n### Hotels\nThe cap is 250 dollars. Book early.\n\n"
                 "### Meals\nThe allowance is 75 dollars. Tips are included.\n")


def test_fixed_windows_have_size_and_overlap():
    doc = Doc("n.md", " ".join(f"w{i}" for i in range(25)))
    chunks = fixed(doc, size=10, overlap=3)
    assert [c.text.split()[0] for c in chunks] == ["w0", "w7", "w14", "w21"]
    assert all(c.words == 10 for c in chunks[:-1]) and chunks[-1].text.split()[-1] == "w24"
    with pytest.raises(ValueError):
        fixed(doc, size=10, overlap=10)


def test_sentence_chunks_never_cut_a_sentence():
    text = "One two three. Four five six seven. Eight nine. Ten eleven twelve thirteen fourteen."
    chunks = sentence(Doc("s.md", text), size=6)
    assert [c.text for c in chunks] == ["One two three.", "Four five six seven. Eight nine.",
                                        "Ten eleven twelve thirteen fourteen."]
    assert sentences("Kept for 1.5 years. Done.") == ["Kept for 1.5 years.", "Done."]


def test_sections_track_the_heading_path():
    got = sections(MD.text)
    assert [p for p, _ in got] == [["Policy"], ["Policy", "Travel", "Hotels"], ["Policy", "Travel", "Meals"]]
    assert got[1][1] == "The cap is 250 dollars. Book early."


def test_heading_path_goes_in_the_index_not_the_body():
    hotels = heading(MD)[1]
    assert hotels.heading == "Policy > Travel > Hotels"
    assert "Hotels" in hotels.index_text and "Hotels" not in hotels.text


def test_no_strategy_loses_or_invents_words():
    for doc in load_docs(ROOT / "docs"):
        expected = plain(doc.text).split()
        for fn in (sentence, heading):
            assert " ".join(c.text for c in fn(doc, 50)).split() == expected
        # fixed windows overlap, but stitching each window's new words back together recovers the text
        w = fixed(doc, 50, 10)
        assert w[0].text.split() + [x for c in w[1:] for x in c.text.split()[10:]] == expected


def test_tokenizer_drops_stopwords_and_strips_suffixes():
    assert tokenize("How often are the Hotels booked?") == ["hotel", "book"]
    assert tokenize("SEV2 pages") == ["sev2", "pag"]


def test_bm25_prefers_rare_matching_terms_and_normalizes_length():
    texts = ["hotel cap is 250 dollars", "meals and tips and travel and travel", "travel " * 30 + "hotel"]
    index = BM25(texts)
    assert index.search("hotel cap", 3)[0] == 0
    assert index.scores("hotel")[0] > index.scores("hotel")[2]  # same tf, the long chunk is penalized
    assert index.scores("submarine") == [0.0, 0.0, 0.0]


def test_answer_split_across_chunks_is_a_miss():
    q = Question("cap?", "t.md", "The cap is 250 dollars")
    assert contains_answer(Chunk("t.md", "The cap is 250 dollars per night"), q)
    assert not contains_answer(Chunk("t.md", "The cap is 250"), q)
    assert not contains_answer(Chunk("other.md", "The cap is 250 dollars"), q)
    # windows [a b c d The cap] [cap is 250 dollars.] cut the answer in half: no chunk can answer
    assert [c.text for c in fixed(Doc("t.md", "a b c d The cap is 250 dollars."), 6)][1] == "cap is 250 dollars."
    r = evaluate([Doc("t.md", "a b c d The cap is 250 dollars.")], [q], "fixed", size=6)
    assert r.unanswerable == 1 and r.recall[5] == 0


def test_recall_is_monotone_in_k_and_mrr_matches_ranks():
    docs, qs = load_docs(ROOT / "docs"), load_questions(ROOT / "data" / "questions.json")
    for strategy in ("fixed", "sentence", "heading"):
        r = evaluate(docs, qs, strategy, 100)
        assert r.recall[1] <= r.recall[3] <= r.recall[5]
        assert r.mrr == pytest.approx(sum(1 / x for x in r.ranks if x) / len(qs))


def test_every_gold_answer_is_in_its_document():
    docs = {d.name: " ".join(d.text.split()) for d in load_docs(ROOT / "docs")}
    qs = load_questions(ROOT / "data" / "questions.json")
    assert len(qs) >= 40
    for q in qs:
        assert q.answer in docs[q.doc], q.q


def test_heading_chunks_beat_fixed_at_rank_one_with_less_context():
    docs, qs = load_docs(ROOT / "docs"), load_questions(ROOT / "data" / "questions.json")
    fx, hd = evaluate(docs, qs, "fixed", 100), evaluate(docs, qs, "heading", 100)
    assert hd.recall[1] > fx.recall[1] + 0.1
    assert hd.context_words < fx.context_words / 2
