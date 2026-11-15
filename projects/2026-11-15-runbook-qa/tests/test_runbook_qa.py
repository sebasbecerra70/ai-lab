from pathlib import Path

import pytest

from runbook_qa import BM25, MockLLM, RunbookQA, check, load_runbooks, validate

DATA = Path(__file__).resolve().parent.parent / "data" / "runbooks"


@pytest.fixture(scope="module")
def procs():
    return load_runbooks(DATA)


@pytest.fixture
def qa(procs):
    return RunbookQA(procs, MockLLM())


def test_loader_splits_procedures_and_steps(procs):
    assert len(procs) == 10
    pdu = next(p for p in procs if p.title == "PDU breaker trip")
    assert pdu.id == "power_distribution#pdu-breaker-trip"
    assert len(pdu.steps) == 6 and pdu.step_id(4) == "power_distribution#pdu-breaker-trip:4"


@pytest.mark.parametrize("question,expected", [
    ("PDU breaker tripped", "power_distribution#pdu-breaker-trip"),
    ("chilled water leak alarm", "cooling#chilled-water-leak-detected"),
    ("replace a failed disk", "hardware#failed-disk-replacement"),
    ("UPS running on battery", "ups_battery#ups-on-battery-alarm"),
])
def test_bm25_ranks_the_right_procedure_first(procs, question, expected):
    assert BM25(procs).search(question)[0][0].id == expected


def test_answer_cites_only_retrieved_steps(qa):
    a = qa.ask("A PDU breaker tripped, what do I do?")
    assert a.status == "answered" and a.source == "llm"
    assert a.citations[0] == "power_distribution#pdu-breaker-trip:1"
    assert "Do not reset a breaker more than once" in a.text  # warnings are kept, not summarized away


def test_hallucinated_citation_falls_back_to_extractive(procs):
    a = RunbookQA(procs, MockLLM(hallucinate=True)).ask("A PDU breaker tripped, what do I do?")
    assert a.source == "extractive"
    assert any(":99" in p for p in a.problems)
    assert "Power-cycle the whole row" not in a.text


def test_validator_flags_uncited_steps():
    problems = validate("1. Reset the breaker.\n2. Watch the load. [x#y:2]", {"x#y:2"})
    assert problems == ["uncited step: 1. Reset the breaker."]
    assert validate("Sure, just reset it.", set()) == ["no numbered steps"]


def test_guard_refuses_repeat_breaker_reset_with_the_rule(qa):
    a = qa.ask("The breaker keeps tripping, can I reset it again?")
    assert a.status == "refused"
    assert a.citations == ["power_distribution#pdu-breaker-trip:4"]


def test_guard_refuses_lockout_bypass(qa):
    a = qa.ask("How do I remove another tech's lock?")
    assert a.status == "refused" and "Never bypass or remove another person's lock" in a.text


def test_guard_does_not_block_normal_questions(procs):
    assert check("UPS on battery, generator not started", procs) is None
    assert check("how do I do lockout tagout correctly", procs) is None


def test_off_topic_question_is_not_covered(qa):
    a = qa.ask("How do I renew the SSL certificate on the customer portal?")
    assert a.status == "not_covered" and a.citations == []


def test_model_can_decline(procs):
    class Declines:
        def complete(self, system, prompt):
            return "NOT_COVERED"
    assert RunbookQA(procs, Declines()).ask("UPS on battery alarm").status == "not_covered"
