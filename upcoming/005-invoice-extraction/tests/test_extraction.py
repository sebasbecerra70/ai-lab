import json
from pathlib import Path

import pytest

from invoice_extract import InvoiceExtractor, RecordedLLM, parse_date, parse_json_object, regex_extract, validate

DATA = Path(__file__).resolve().parent.parent / "data"
INVOICES = DATA / "invoices"


def good_invoice(**overrides):
    inv = {"vendor": "V", "invoice_number": "X-1", "invoice_date": "2026-01-10", "due_date": "2026-02-09",
           "currency": "USD", "subtotal": 30.0, "tax": 3.0, "total": 33.0,
           "line_items": [{"description": "a", "quantity": 2, "unit_price": 10.0, "amount": 20.0},
                          {"description": "b", "quantity": 1, "unit_price": 10.0, "amount": 10.0}]}
    inv.update(overrides)
    return inv


def test_parse_json_object_tolerates_fences_and_preambles():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure! Here it is: {"a": {"b": 2}} hope that helps') == {"a": {"b": 2}}
    assert parse_json_object('{"a": [1, 2') is None
    assert parse_json_object("no json here") is None


def test_parse_date_formats():
    cases = {"2026-03-02": "2026-03-02", "03/05/2026": "2026-03-05", "14 Mar 2026": "2026-03-14",
             "March 18, 2026": "2026-03-18", "not a date": None}
    assert {raw: parse_date(raw) for raw in cases} == cases


def test_validator_accepts_a_consistent_invoice():
    assert validate(good_invoice()) == {}


def test_validator_catches_business_rule_violations():
    assert "total" in validate(good_invoice(total=33.3))
    assert "subtotal" in validate(good_invoice(subtotal=31.0, total=34.0))
    assert "currency" in validate(good_invoice(currency="DOGE"))
    assert "due_date" in validate(good_invoice(due_date="2026-01-01"))
    assert "invoice_date" in validate(good_invoice(invoice_date="03/05/2026"))
    bad_line = good_invoice(line_items=[{"description": "a", "quantity": 2, "unit_price": 10.0, "amount": 25.0}])
    assert "line_items" in validate(bad_line)
    assert validate({"vendor": "V"})["total"] == "missing"


@pytest.mark.parametrize("name, number, total, lines", [
    ("acme_freight.txt", "AF-20931", 3420.00, 3), ("brightpack.txt", "BP-7781", 1143.12, 3),
    ("nordic_cold.txt", "NCC-2026-0412", 2226.25, 2), ("delta_parts.txt", "DIP-11873", 868.80, 3),
])
def test_regex_fallback_reads_every_sample_layout(name, number, total, lines):
    out = regex_extract((INVOICES / name).read_text())
    assert out["invoice_number"] == number
    assert out["total"] == pytest.approx(total)
    assert len(out["line_items"]) == lines
    assert validate(out) == {}


@pytest.fixture
def extractor():
    return InvoiceExtractor(RecordedLLM.from_file(DATA / "mock_responses.json"))


def test_clean_llm_output_is_used_as_is(extractor):
    r = extractor.extract((INVOICES / "acme_freight.txt").read_text())
    assert r.status == "ok" and set(r.sources.values()) == {"llm"}


def test_non_iso_date_from_llm_is_normalized(extractor):
    r = extractor.extract((INVOICES / "brightpack.txt").read_text())
    assert r.data["invoice_date"] == "2026-03-05" and r.sources["invoice_date"] == "llm"


def test_hallucinated_total_is_replaced_by_regex_value(extractor):
    r = extractor.extract((INVOICES / "nordic_cold.txt").read_text())
    assert r.llm_errors == {"total": "does not equal subtotal + tax"}
    assert r.data["total"] == 2226.25 and r.sources["total"] == "regex"
    assert r.sources["vendor"] == "llm"  # fields that validated are not touched
    assert r.status == "ok"


def test_truncated_llm_reply_falls_back_entirely_to_regex(extractor):
    r = extractor.extract((INVOICES / "delta_parts.txt").read_text())
    assert "_" in r.llm_errors and set(r.sources.values()) == {"regex"}
    assert r.status == "ok" and r.data["po_number"] == "PO-55230"


def test_flags_for_review_when_neither_path_can_fix_it():
    text = "Mystery Vendor\nInvoice No: MV-1\nDate: 2026-02-01\nTotal: $50.00\nSubtotal 40.00\nTax 5.00\n"
    llm = RecordedLLM({"MV-1": json.dumps({"vendor": "Mystery Vendor", "invoice_number": "MV-1",
                                           "invoice_date": "2026-02-01", "currency": "USD",
                                           "subtotal": 40.0, "tax": 5.0, "total": 50.0})})
    r = InvoiceExtractor(llm).extract(text)
    assert r.status == "needs_review" and "total" in r.errors
