from pathlib import Path

import pytest

from clause_extractor import (Clause, MockLLM, analyze, analyze_dir, assess, classify, extract_fields, our_role,
                              parse_llm, split_clauses)

DATA = Path(__file__).resolve().parent.parent / "data" / "contracts"
ACME = (DATA / "acme_reseller.txt").read_text()


def test_split_clauses_and_role():
    clauses = split_clauses(ACME)
    assert [c.number for c in clauses] == list(range(1, 10))
    assert clauses[3].heading == "Term and Renewal"
    assert our_role(ACME) == "Partner"


@pytest.mark.parametrize("heading, text, expected", [
    ("Term and Renewal", "shall automatically renew for successive periods", "renewal"),
    ("Liability", "Marketplace shall have no liability for indirect damages", "liability"),
    ("Indemnity", "Seller shall indemnify Marketplace", "indemnification"),
    ("Miscellaneous", "Either party may terminate for breach", "termination"),
    ("Definitions", "Products means the software", "other"),
])
def test_rule_classifier(heading, text, expected):
    assert classify(Clause(1, heading, text)) == expected


def test_renewal_fields_parse_word_numbers():
    f = extract_fields("renewal", "shall automatically renew for successive one (1) year periods unless notice "
                                  "at least one hundred twenty (120) days before the end", "Partner")
    assert f == {"auto_renew": True, "renewal_months": 12, "notice_days": 120}


def test_liability_detects_our_uncapped_exposure():
    f = extract_fields("liability", "VENDOR'S LIABILITY EXCEED THE FEES PAID IN THE THREE (3) MONTHS. "
                                    "PARTNER'S LIABILITY SHALL BE UNLIMITED.", "Partner")
    assert f["cap_months"] == 3 and f["we_are_uncapped"]


def test_payment_direction_matters():
    assert extract_fields("payment", "Partner shall pay invoices net ninety (90) days", "Partner")["we_are_payee"] is False
    assert extract_fields("payment", "Payouts to Seller are made within sixty (60) days", "Seller")["we_are_payee"] is True


def test_parse_llm_rejects_off_contract_output():
    assert parse_llm('```json\n{"type": "renewal", "confidence": 0.8}\n```')["type"] == "renewal"
    assert parse_llm("I think it's a renewal clause") is None
    assert parse_llm('{"type": "warranty", "confidence": 0.9}') is None
    assert parse_llm('{"type": "renewal", "confidence": 7}') is None


def test_fallback_to_rules_when_llm_output_is_bad():
    report = analyze("acme", ACME, MockLLM(fail_on={4, 7}))
    by_num = {c.number: c for c in report.clauses}
    assert by_num[4].source == "rules" and by_num[4].type == "renewal"
    assert report.fallbacks == [4, 7]


def test_rules_only_mode_without_llm():
    report = analyze("acme", ACME, None)
    assert all(c.source == "rules" for c in report.clauses)
    assert report.fallbacks == []


def test_disagreement_is_surfaced_for_review():
    class Contrarian:
        def complete(self, system, prompt):
            return '{"type": "confidentiality", "confidence": 0.95}'
    report = analyze("acme", ACME, Contrarian())
    assert 4 in report.disagreements  # renewal clause labeled confidentiality


def test_risk_flags_for_acme():
    msgs = [(f.severity, f.clause) for f in analyze("acme", ACME, MockLLM()).flags]
    assert ("high", 5) in msgs  # vendor-only termination for convenience
    assert ("high", 7) in msgs  # our liability uncapped
    assert ("medium", 4) in msgs  # 120-day renewal notice


def test_balanced_contract_has_no_flags_and_ranking():
    reports = {r.name: r for r in analyze_dir(DATA, MockLLM())}
    assert reports["brightline_msa"].flags == []
    assert reports["cobalt_marketplace"].score > reports["brightline_msa"].score
    assert assess([], "Client") == []
