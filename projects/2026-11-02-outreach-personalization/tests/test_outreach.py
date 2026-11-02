import io
import json
from pathlib import Path

import pytest

from outreach import (SYSTEM, AnthropicClient, MockLLM, build_prompt, draft_email, failures, parse_email,
                      personalization_tokens, pick_proof, run_checks)

DATA = Path(__file__).resolve().parent.parent / "data"
PRODUCT = json.loads((DATA / "product.json").read_text())
PROSPECTS = json.loads((DATA / "prospects.json").read_text())
DANA = PROSPECTS[0]


def clean_email():
    return json.loads(MockLLM().complete(SYSTEM, build_prompt(DANA, PRODUCT, feedback=[], previous={}) + "REVIEWER FEEDBACK"))


def failed(email, prospect=DANA):
    return {c.name for c in failures(run_checks(email, prospect, PRODUCT))}


def test_clean_mock_email_passes_every_check():
    assert failed(clean_email()) == set()


def test_banned_claims_match_whole_phrases_case_insensitively():
    e = clean_email()
    e["body"] = e["body"].replace("We work with", "Results GUARANTEED. We work with")
    assert failed(e) == {"no banned claims"}
    e = clean_email()
    e["body"] = e["body"].replace("Hi Dana", "Hi Dana (no guarantees implied)")  # 'guarantees' is not 'guarantee'
    assert "no banned claims" not in failed(e)


def test_invented_numbers_are_caught_but_facts_from_the_brief_are_allowed():
    e = clean_email()
    assert "31%" in e["body"]  # from an approved proof point
    e["body"] = e["body"].replace("in two quarters", "in two quarters and 18% in a third")
    checks = {c.name: c for c in run_checks(e, DANA, PRODUCT)}
    assert not checks["numbers grounded"].passed and "18%" in checks["numbers grounded"].detail


def test_personalization_needs_name_company_and_trigger():
    assert personalization_tokens(DANA)["trigger"] == ["second", "cross", "columbus"]
    e = clean_email()
    e["body"] = e["body"].replace("Northstar Fresh opened a second cross-dock in Columbus", "your team is growing")
    e["body"] = e["body"].replace("fits Northstar Fresh", "fits you")
    assert failed(e) == {"personalized"}


def test_placeholders_length_cta_subject_and_opt_out():
    e = clean_email()
    e["body"] = e["body"].replace("Hi Dana", "Hi [First Name]").replace(PRODUCT["footer"], "")
    e["subject"] = "HUGE SAVINGS for you!"
    assert {"no placeholders", "opt-out line", "subject"} <= failed(e)
    short = {"subject": "Hi", "body": "Hi Dana at Northstar Fresh, about Columbus: call?\n" + PRODUCT["footer"]}
    assert "length" in failed(short)
    e = clean_email()
    e["body"] = e["body"].replace("Northstar Fresh?", "Northstar Fresh? Or next month?")
    assert "one call to action" in failed(e)


def test_parse_email_tolerates_fences_and_prose():
    assert parse_email('Sure!\n```json\n{"subject": "a", "body": "b"}\n```')["subject"] == "a"
    assert parse_email("not json") == {"subject": "", "body": "not json"}


def test_revise_loop_fixes_flawed_first_drafts():
    drafts = [draft_email(MockLLM(), p, PRODUCT) for p in PROSPECTS]
    assert sum(d.first_pass for d in drafts) < len(drafts)  # the mock injects real failure modes
    assert all(d.passed for d in drafts)
    assert all(len(d.attempts) <= 3 for d in drafts)


def test_revision_prompt_carries_the_failed_checks_and_previous_draft():
    seen = []

    class Recorder(MockLLM):
        def complete(self, system, prompt):
            seen.append(prompt)
            return super().complete(system, prompt)

    d = draft_email(Recorder(), DANA, PRODUCT)
    assert len(seen) == len(d.attempts) == 2
    assert "REVIEWER FEEDBACK" in seen[1] and "no banned claims: guarantee" in seen[1]
    assert "guarantee" in seen[1].split("Previous draft:")[1]


def test_loop_gives_up_after_max_revisions():
    class Stubborn:
        def complete(self, system, prompt):
            return json.dumps({"subject": "x", "body": "We guarantee it."})

    d = draft_email(Stubborn(), DANA, PRODUCT, max_revisions=2)
    assert not d.passed and len(d.attempts) == 3


def test_pick_proof_and_anthropic_request_shape(monkeypatch):
    assert "pharma" in pick_proof("specialty pharma", PRODUCT["proof_points"])["customer"]
    captured = {}

    def fake_urlopen(req, timeout):
        captured.update(url=req.full_url, headers=dict(req.header_items()), body=json.loads(req.data))
        return io.BytesIO(json.dumps({"content": [{"type": "text", "text": "{}"}]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert AnthropicClient(api_key="k").complete("sys", "hi") == "{}"
    assert captured["headers"]["Anthropic-version"] == "2023-06-01"
    assert captured["body"]["model"] == "claude-sonnet-5-5" and captured["body"]["system"] == "sys"
