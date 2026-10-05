from pathlib import Path

import pytest

from sop_rag import Chunk, MockLLM, SOPAssistant, TfidfRetriever
from sop_rag.retriever import chunk_markdown, tokenize

DOCS = Path(__file__).resolve().parent.parent / "docs"


@pytest.fixture(scope="module")
def retriever():
    return TfidfRetriever.from_directory(DOCS)


def test_tokenize_drops_stopwords_and_punctuation():
    assert tokenize("The trailer's SEAL, and the door!") == ["trailer", "seal", "door"]


def test_chunk_markdown_splits_on_headings():
    chunks = chunk_markdown("x.md", "# T\nintro\n## A\none\n## B\ntwo")
    assert [c.text.splitlines()[0] for c in chunks] == ["# T", "## A", "## B"]


@pytest.mark.parametrize(
    "question, expected_heading",
    [
        ("What temperature for frozen loads?", "## Frozen and refrigerated loads"),
        ("pallet arrived damaged, what do I do", "## Damaged inbound pallets"),
        ("seal number broken", "## Seal verification"),
        ("hazmat placards", "## Hazmat"),
    ],
)
def test_retrieves_the_right_section(retriever, question, expected_heading):
    top, score = retriever.search(question, k=1)[0]
    assert top.text.startswith(expected_heading)
    assert score > 0


def test_unrelated_query_returns_nothing(retriever):
    assert retriever.search("quantum chromodynamics") == []


def test_assistant_answers_with_citation(retriever):
    answer = SOPAssistant(retriever, MockLLM()).ask("What temperature for frozen loads?")
    assert "0°F" in answer.text and "[1]" in answer.text
    assert answer.sources[0].source == "receiving.md"


def test_assistant_refuses_without_grounding(retriever):
    answer = SOPAssistant(retriever, MockLLM()).ask("What is the CEO's favorite color?")
    assert answer.text.startswith("I don't know")
    assert answer.sources == []


def test_empty_corpus_rejected():
    with pytest.raises(ValueError):
        TfidfRetriever([])


def test_prompt_passed_to_llm_contains_numbered_context(retriever):
    class Spy:
        def complete(self, system, prompt):
            self.system, self.prompt = system, prompt
            return "ok"

    spy = Spy()
    SOPAssistant(retriever, spy).ask("load sequencing heavy pallets")
    assert "[1] source: shipping.md" in spy.prompt
    assert "ONLY" in spy.system
