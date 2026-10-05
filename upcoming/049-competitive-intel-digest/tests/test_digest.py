import json
from pathlib import Path

import pytest

from intel_digest import MockLLM, audit, build_prompt, clean_lines, diff_all, page_diff, pricing_diff, write_digest

DATA = Path(__file__).resolve().parent.parent / "data"
US = json.loads((DATA / "us.json").read_text())


@pytest.fixture(scope="module")
def changes():
    return diff_all(DATA / "prev", DATA / "curr", watch=set(US["differentiators"]))


def plan(name, price, features=(), **limits):
    return {"name": name, "price": price, "unit": "seat/mo", "features": list(features), "limits": limits}


def test_price_change_severity_by_size():
    small = pricing_diff("x", {"plans": [plan("Pro", 100)]}, {"plans": [plan("Pro", 103)]})
    big = pricing_diff("x", {"plans": [plan("Pro", 100)]}, {"plans": [plan("Pro", 80)]})
    assert (small[0].kind, small[0].severity) == ("price_increase", "medium")
    assert (big[0].kind, big[0].severity) == ("price_decrease", "high")
    assert "(-20%)" in big[0].detail


def test_plans_added_and_removed():
    out = pricing_diff("x", {"plans": [plan("Pro", 10), plan("Legacy", 5)]}, {"plans": [plan("Pro", 10), plan("Scale", 30)]})
    kinds = sorted(c.kind for c in out)
    assert kinds == ["plan_added", "plan_removed"]
    assert all(c.severity == "high" for c in out)


def test_features_on_our_watch_list_are_high_severity():
    out = pricing_diff("x", {"plans": [plan("Pro", 10, ["A"])]}, {"plans": [plan("Pro", 10, ["A", "SSO", "AI reply drafts"])]},
                       watch={"AI reply drafts"})
    sev = {c.detail: c.severity for c in out}
    assert sev == {"Pro gains SSO": "medium", "Pro gains AI reply drafts": "high"}


def test_limit_changes_read_unlimited_and_direction():
    out = pricing_diff("x", {"plans": [plan("Pro", 10, seats=10)]}, {"plans": [plan("Pro", 10, seats=None)]})
    assert out[0].detail == "Pro seats: 10 -> unlimited (more generous)"


def test_noise_lines_and_whitespace_are_ignored():
    assert clean_lines("Hello   world\nUpdated 3 days ago\n© Acme Inc\n\nCookie preferences") == ["Hello world"]
    assert page_diff("x", "home", "# A\nAutomate  ops.\nUpdated 1 day ago", "# A\nAutomate ops.\nUpdated 4 days ago") == []


def test_page_edits_are_classified():
    prev = "# Acme\nThe shared inbox for teams.\nTrusted by 2,000+ teams.\nFast setup."
    curr = "# Acme\nThe AI-first help desk.\nTrusted by 2,500+ teams.\nFast setup.\nNow with SOC 2."
    kinds = {c.kind: c.severity for c in page_diff("acme", "home", prev, curr)}
    assert kinds == {"positioning": "high", "claim_change": "medium", "copy_added": "medium"}


def test_sample_changes_are_ranked_and_numbered(changes):
    assert [c.id for c in changes] == [f"C{i}" for i in range(1, len(changes) + 1)]
    ranks = [{"high": 0, "medium": 1, "low": 2}[c.severity] for c in changes]
    assert ranks == sorted(ranks)
    assert not any(c.competitor == "opsforge" and c.severity != "low" for c in changes)
    assert any(c.kind == "price_increase" and "+27%" in c.detail for c in changes)


def test_prompt_lists_every_change_with_its_id(changes):
    p = build_prompt(changes, US)
    assert all(f"[{c.id}] " in p for c in changes)
    assert "OUR DIFFERENTIATORS: AI reply drafts" in p


def test_mock_digest_cites_all_high_changes_and_compares_prices(changes):
    text, a = write_digest(MockLLM(), changes, US)
    assert a.ok
    assert "Growth is now $3 above our Growth price" in text
    assert "opsforge" not in text  # only low-severity noise there


def test_audit_catches_made_up_ids_and_skipped_highs(changes):
    a = audit("RelayDesk cut prices [C99].", changes)
    assert a.unknown == ["C99"]
    assert len(a.uncited_high) == sum(c.severity == "high" for c in changes)
