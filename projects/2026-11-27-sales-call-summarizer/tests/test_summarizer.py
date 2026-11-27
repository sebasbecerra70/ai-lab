import json
from pathlib import Path

import pytest

from call_summarizer import (FIELDS, Assessment, Call, Field, MockLLM, build_prompt, extract, health, load,
                             quote_in, score)
from call_summarizer.meddic import stakeholders

CALLS = Path(__file__).resolve().parent.parent / "data" / "calls"


class FixedLLM:
    def __init__(self, reply: str):
        self.reply = reply

    def complete(self, system: str, prompt: str) -> str:
        return self.reply


def assessment(stage="Evaluation", statuses=None, **kw):
    statuses = statuses or {}
    fields = {f: Field(f, statuses.get(f, "confirmed"), "", "") for f in FIELDS}
    opts = dict(competitors=[], budget_allocated=True, timeline_risk=False, single_threaded=False)
    opts.update(kw)
    return Assessment(Call("x", "Acme", stage, 100_000), fields, **opts)


def test_load_parses_header_and_marks_seller_turns():
    call = load(CALLS / "northwind_discovery2.txt")
    assert (call.deal, call.stage, call.amount) == ("Northwind Labs", "Evaluation", 180_000)
    assert call.customer_speakers == ["Priya"]
    assert all(t.is_seller for t in call.turns if t.speaker == "Jordan")
    assert len(call.turns) == 17


def test_quote_check_ignores_punctuation_but_rejects_seller_and_invented_quotes():
    call = load(CALLS / "northwind_discovery2.txt")
    assert quote_in(call, "our CFO Mark Ellis approves anything over 100k")
    # the seller said this, so it can't count as customer evidence
    assert not quote_in(call, "how would you measure success")
    assert not quote_in(call, "Mark already signed the contract")
    assert not quote_in(call, "")


def test_prompt_labels_customer_and_seller_lines():
    prompt = build_prompt(load(CALLS / "cobalt_intro.txt"))
    assert prompt.startswith("DEAL: Cobalt Foods\nSTAGE: Discovery")
    assert "SELLER Jordan: Thanks for joining" in prompt
    assert "CUSTOMER Lena: My manager asked me" in prompt


def test_fabricated_evidence_is_downgraded_to_unverified():
    llm = MockLLM(fabricate={"economic_buyer": "Cobalt Foods|Our finance director owns this budget and will sign."})
    a = extract(llm, load(CALLS / "cobalt_intro.txt"))
    assert a.fields["economic_buyer"].status == "unverified"
    # unverified earns no credit, the same as missing
    honest = extract(MockLLM(), load(CALLS / "cobalt_intro.txt"))
    assert honest.fields["economic_buyer"].status == "partial"
    assert a.score < honest.score


def test_strong_deal_confirms_all_fields_and_scores_healthy():
    a = extract(MockLLM(), load(CALLS / "harbor_negotiation.txt"))
    assert all(a.fields[f].status == "confirmed" for f in FIELDS)
    assert not a.single_threaded  # Dev names Maria as champion
    assert a.timeline_risk and a.risks == ["timeline risk raised on the call"]
    assert a.score == 95 and health(a.score) == "healthy"
    assert a.stage_gaps == [] and a.actions == []


def test_weak_deal_gets_risks_stage_gaps_and_actions():
    a = extract(MockLLM(), load(CALLS / "cobalt_intro.txt"))
    assert a.competitors == ["Nlyte", "Sunbird"]
    assert not a.budget_allocated and a.single_threaded
    assert a.stage_gaps == ["identify_pain"]
    assert a.actions[0].startswith("Find the business event")
    assert health(a.score) == "at risk"


def test_score_is_weighted_coverage_times_risk_multipliers():
    a = score(assessment(statuses={"champion": "partial", "metrics": "missing"}))
    assert a.score == round(100 - 15 - 15 * 0.6)  # 76
    a = score(assessment(competitors=["Sunbird", "Nlyte", "Device42"], budget_allocated=False))
    # competitor penalty is capped at 20%
    assert a.score == round(100 * 0.8 * 0.8)
    assert a.risks == ["competing with Sunbird, Nlyte, Device42", "no budget allocated"]


def test_stage_gaps_follow_the_deal_stage():
    statuses = {"champion": "partial", "decision_process": "missing"}
    assert score(assessment("Evaluation", statuses)).stage_gaps == []
    neg = score(assessment("Negotiation", statuses))
    assert neg.stage_gaps == ["decision_process", "champion"]
    assert len(neg.actions) == 2


def test_stakeholder_detection_finds_named_contacts():
    text = "Sam from facilities will run it. Our CFO, Mark Ellis, approves. Maria, our lead, presented."
    assert stakeholders(text) == {"Sam", "Mark", "Maria"}


def test_model_reply_with_prose_around_json_is_parsed_and_missing_fields_default():
    reply = "Here is the analysis:\n" + json.dumps({"metrics": {"status": "confirmed", "summary": "s",
                                                               "evidence": "240 thousand dollars"}}) + "\nDone."
    a = extract(FixedLLM(reply), load(CALLS / "northwind_discovery2.txt"))
    assert a.fields["metrics"].status == "confirmed"
    assert a.fields["champion"].status == "missing"
    with pytest.raises(ValueError):
        extract(FixedLLM("I could not parse the call."), load(CALLS / "northwind_discovery2.txt"))


def test_health_bands():
    assert [health(s) for s in (90, 75, 74, 50, 49)] == ["healthy", "healthy", "watch", "watch", "at risk"]

