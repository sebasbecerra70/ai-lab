import json
from pathlib import Path

import pytest

from account_agent import DocStore, MockLLM, ResearchAgent, check_citations, extract_signals, score_fit, tokenize

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def store():
    return DocStore.from_dir(DATA)


class Scripted:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def complete(self, system, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def test_tokenize_drops_stopwords():
    assert tokenize("The DC of Harbor, and its S/4HANA") == ["dc", "harbor", "s", "4hana"]


def test_store_loads_sections_and_titles(store):
    assert store.titles["harbor_retail"] == "Harbor Retail"
    assert store.get("harbor_retail", "recent news").ref == "harbor_retail#Recent news"
    with pytest.raises(KeyError, match="available: Overview"):
        store.get("harbor_retail", "Board")


def test_bm25_finds_the_pain_section(store):
    top, _ = store.search("stockouts lost sales", doc="harbor_retail")[0]
    assert top.heading == "Recent news"
    assert all(s.doc == "pinnacle_steel" for s, _ in store.search("inventory", doc="pinnacle_steel"))


def test_signals_parse_numbers_with_units(store):
    sig = {(s["signal"], s["value"]) for s in extract_signals(store, "harbor_retail")}
    assert ("locations", 212) in sig
    assert ("revenue", 2.4e9) in sig and ("inventory", 610e6) in sig
    assert ("skus", 1800) in {(s["signal"], s["value"]) for s in extract_signals(store, "pinnacle_steel")}


def test_fit_scores_rank_accounts_sensibly(store):
    scores = {d: score_fit(store, d)["score"] for d in ("harbor_retail", "juniper_pharma", "pinnacle_steel", "evergreen_foods")}
    assert max(scores, key=scores.get) == "harbor_retail"
    unmet = [r for r in score_fit(store, "harbor_retail")["reasons"] if not r["met"]]
    assert [r["criterion"] for r in unmet] == ["10k+ SKUs"] and unmet[0]["ref"] is None


def test_agent_runs_the_research_plan_and_grounds_the_brief(store):
    result = ResearchAgent(MockLLM(), store).run("Harbor Retail")
    assert [s.tool for s in result.steps] == ["list_companies", "read_section", "score_fit", "read_section", "read_section",
                                              "search", "read_section"]
    for heading in ("Snapshot", "Fit: 3/4", "Why now", "Pains and plays", "Who to talk to", "Suggested opener"):
        assert f"## {heading}" in result.brief
    assert "$45M" in result.brief and "Priya Raman" in result.brief
    check = check_citations(result.brief, result.seen_refs)
    assert check["unseen"] == [] and check["uncited_bullets"] == []


def test_unknown_account_ends_without_inventing_a_brief(store):
    result = ResearchAgent(MockLLM(), store).run("Globex Corp")
    assert len(result.steps) == 1
    assert "No profile found" in result.brief


def test_tool_errors_are_fed_back_to_the_model(store):
    llm = Scripted(
        json.dumps({"tool": "read_section", "args": {"doc": "harbor_retail", "section": "Board"}}),
        json.dumps({"tool": "teleport", "args": {}}),
        json.dumps({"final": "done"}),
    )
    result = ResearchAgent(llm, store).run("Harbor Retail")
    assert "available: Overview" in result.steps[0].observation["error"]
    assert result.steps[1].observation == {"error": "unknown tool 'teleport'"}
    assert '"error"' in llm.prompts[2]  # the model saw both errors in its history
    assert result.brief == "done"


def test_step_budget_stops_a_looping_model(store):
    loop = json.dumps({"tool": "list_companies", "args": {}})
    result = ResearchAgent(Scripted(*[loop] * 3), store, max_steps=3).run("Harbor Retail")
    assert result.stopped == "max_steps" and len(result.steps) == 3


def test_citation_check_flags_unseen_and_missing_sources():
    brief = "- revenue $2.4B [harbor_retail#Financials]\n- big DC coming\n- CEO likes us [harbor_retail#Board]"
    check = check_citations(brief, {"harbor_retail#Financials"})
    assert check["unseen"] == ["harbor_retail#Board"]
    assert check["uncited_bullets"] == ["- big DC coming"]
