from pathlib import Path

import pytest

from rfp_rag import BM25, ExtractiveLLM, Passage, RFPDrafter, build_prompt, check_citations, load_passages, tokenize

DOCS = Path(__file__).resolve().parent.parent / "docs" / "proposals"


@pytest.fixture(scope="module")
def index():
    return BM25(load_passages(DOCS))


def test_tokenize_drops_rfp_boilerplate_and_maps_buyer_vocabulary():
    assert tokenize("Please describe your SSO options") == ["sign", "option"]
    assert tokenize("one warehouse") == ["one", "site"]


def test_chunking_is_one_passage_per_question(index):
    assert len(index.passages) == 11
    p = next(p for p in index.passages if "disaster recovery" in p.question)
    assert p.source == "contoso_tms.md" and "RPO" in p.answer


@pytest.mark.parametrize("question, expected_source, expected_q", [
    ("What are your RPO and RTO?", "contoso_tms.md", "disaster recovery"),
    ("How long does implementation take for one warehouse?", "northwind_wms.md", "implementation timeline"),
    ("Is data encrypted at rest?", "northwind_wms.md", "encrypted"),
])
def test_bm25_finds_the_right_past_answer(index, question, expected_source, expected_q):
    top = index.search(question, 1)[0][0]
    assert top.source == expected_source and expected_q in top.question


def test_coverage_is_bounded_and_low_for_unknown_topics(index):
    terms = tokenize("Do you hold FedRAMP authorization?")
    best = max(index.coverage(terms, i) for i in range(len(index.passages)))
    assert 0 <= best < 0.4
    assert index.coverage(tokenize("RPO RTO"), next(i for i, p in enumerate(index.passages) if "RPO" in p.answer)) == 1.0


def test_check_citations_flags_out_of_range_and_uncited():
    assert check_citations("We do [1]. Also this [2].", 2) == []
    issues = check_citations("We do [3]. And we promise more.", 2)
    assert "cites [3] but only 2 source(s) were provided" in issues
    assert any(i.startswith("uncited sentence: And we promise") for i in issues)


def test_draft_with_citations_when_confident(index):
    d = RFPDrafter(index, ExtractiveLLM()).draft("What are your RPO and RTO for disaster recovery?")
    assert d.status == "drafted" and d.confidence == 1.0
    assert "15 minutes" in d.answer and d.citation_issues == []


def test_low_confidence_routes_to_sme_without_calling_llm(index):
    class Exploding:
        def complete(self, system, prompt):
            raise AssertionError("LLM must not be called below the threshold")

    d = RFPDrafter(index, Exploding()).draft("Describe your carbon emissions reporting for shipments.")
    assert d.status == "needs_sme" and d.answer == ""


def test_prompt_numbers_passages_and_llm_hallucinated_citation_is_caught(index):
    passages = [Passage("a.md", "Q one?", "Answer one."), Passage("b.md", "Q two?", "Answer two.")]
    prompt = build_prompt("question?", passages)
    assert prompt.startswith("[1] (a.md)\nQ: Q one?\nA: Answer one.\n[2] (b.md)")

    class Overreaching:
        def complete(self, system, prompt):
            return "We are FedRAMP High authorized [4]."

    d = RFPDrafter(index, Overreaching()).draft("What are your RPO and RTO?")
    assert len(d.citation_issues) == 1 and d.citation_issues[0].startswith("cites [4] but only")


def test_empty_corpus_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_passages(tmp_path)
