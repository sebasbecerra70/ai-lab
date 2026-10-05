import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from deal_desk import (Deal, MockLLM, build_facts, evaluate, fit, load_deals, load_history, load_policy, log_loss,
                       lower_level_discount, margin, review, verify_memo)

DATA = Path(__file__).resolve().parent.parent / "data"
POLICY = load_policy(DATA / "policy.json")
DEALS = {d.id: d for d in load_deals(DATA / "deals.json")}
HISTORY = load_history(DATA / "history.csv")


def deal(**kw):
    base = dict(id="T-1", customer="Test Co", segment="mid-market", product="core", seats=100,
                list_price_per_seat=300, discount=10, term_years=1, annual_prepay=False, competitor=None)
    base.update(kw)
    return Deal(**base)


class Spy:
    def __init__(self, reply=None):
        self.reply, self.prompt = reply, ""

    def complete(self, system, prompt):
        self.prompt = prompt
        return self.reply if self.reply is not None else MockLLM().complete(system, prompt)


def test_ladder_boundaries():
    assert [evaluate(deal(discount=x), POLICY).pricing_role for x in (10, 11, 20, 21, 30, 31)] == \
           ["AE", "Sales Manager", "Sales Manager", "VP Sales", "VP Sales", "CFO"]


def test_allowances_lower_the_effective_discount():
    d = evaluate(deal(discount=20, term_years=3, annual_prepay=True, competitor="Rival"), POLICY)
    assert d.allowances == {"3-year term": 5, "annual prepay": 3, "displacing Rival": 2}
    assert d.effective_discount == 10 and d.pricing_role == "AE"
    assert d.status == "auto-approve"


def test_margin_floor_escalates_and_hard_floor_rejects():
    analytics = deal(product="analytics", list_price_per_seat=420)
    assert margin(analytics, POLICY, 0) == pytest.approx(1 - 95 / 420)
    floor = evaluate(replace(analytics, discount=30), POLICY)   # margin 68%
    assert floor.pricing_role == "CFO" and floor.status == "escalate"
    hard = evaluate(replace(analytics, discount=62), POLICY)    # margin below 55%
    assert hard.status == "reject"


def test_large_deal_and_precedent_raise_the_approver():
    big = evaluate(deal(seats=2000, discount=5), POLICY)
    assert big.pricing_role == "VP Sales" and big.status == "escalate"
    jump = evaluate(deal(discount=19), POLICY, prior_discount=5)
    assert jump.pricing_role == "Sales Manager"
    assert any(f.rule == "precedent" for f in jump.findings)
    # within the allowed jump, an AE-level discount stays with the AE
    assert evaluate(deal(discount=10), POLICY, prior_discount=5).status == "auto-approve"


def test_non_standard_terms_add_side_approvers_or_block():
    d = evaluate(deal(non_standard_terms=["net-90", "MFN", "weird clause"]), POLICY)
    assert d.approvers == ["AE", "Finance", "Legal"] and d.status == "escalate"
    assert evaluate(deal(non_standard_terms=["uncapped liability"]), POLICY).status == "reject"


def test_give_gets_rerun_every_rule():
    # Orion: a 3-year term would satisfy the ladder, but the margin floor still needs the CFO, so no term give-get
    orion = evaluate(DEALS["Q-1043"], POLICY)
    assert not any(g.startswith("with ") for g in orion.give_gets)
    x = lower_level_discount(orion, POLICY)
    assert x == 24
    alt = evaluate(replace(DEALS["Q-1043"], discount=x), POLICY)
    assert alt.pricing_role == "VP Sales" and alt.margin >= POLICY["margin_floor"]
    # Pinecrest: only the combination of 3-year term and prepay brings 18% down to the AE
    pine = evaluate(DEALS["Q-1044"], POLICY)
    assert pine.give_gets[0] == "with a 3-year term with annual prepay, 18% needs only AE"


def test_win_model_learns_the_history_and_saturates():
    model = fit(HISTORY)
    base = sum(r["won"] for r in HISTORY) / len(HISTORY)
    constant = -(base * math.log(base) + (1 - base) * math.log(1 - base))
    assert log_loss(model, HISTORY) < constant
    p = [model.p_win(d, False, "mid-market") for d in (0, 20, 40)]
    assert p[1] > p[0] and p[1] > p[2]  # discount helps, then stops buying wins
    assert model.p_win(15, True, "mid-market") < model.p_win(15, False, "mid-market")


def test_memo_check_catches_invented_numbers_and_missing_approvers():
    d = evaluate(DEALS["Q-1043"], POLICY)
    facts = build_facts(d, None, POLICY)
    good = MockLLM().complete("", "FACTS:\n" + json.dumps(facts))
    assert verify_memo(good, facts) == []
    assert "number not in facts: 82" in verify_memo(good.replace("65%", "82%"), facts)
    assert "approver missing: Legal" in verify_memo(good.replace("Legal", "the lawyers"), facts)


def test_review_falls_back_to_template_when_the_memo_is_ungrounded():
    r = review(DEALS["Q-1044"], POLICY, MockLLM(sloppy={"Q-1044"}), fit(HISTORY), HISTORY)
    assert r.memo_issues and "Sales Manager" in r.memo and "84" not in r.memo
    assert verify_memo(r.memo, r.facts) == []


def test_llm_sees_facts_and_cannot_change_the_decision():
    spy = Spy(reply="Recommendation: auto-approve; approval required from AE.")
    r = review(DEALS["Q-1045"], POLICY, spy, None, HISTORY)
    assert '"status": "reject"' in spy.prompt and "AE says the deal is lost" in spy.prompt
    assert r.decision.status == "reject" and r.memo_issues  # the memo's claim is caught, not obeyed


def test_sample_book_outcomes():
    statuses = {i: review(d, POLICY, MockLLM(), None, HISTORY).decision.status for i, d in DEALS.items()}
    assert statuses == {"Q-1041": "auto-approve", "Q-1042": "escalate", "Q-1043": "escalate",
                        "Q-1044": "escalate", "Q-1045": "reject", "Q-1046": "escalate"}
