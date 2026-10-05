"""Deterministic regex extractor. Less flexible than an LLM, but it never invents a number."""
from __future__ import annotations

import re
from datetime import datetime

_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_AMOUNT = r"([0-9][0-9,]*\.\d{2})"


def parse_amount(text: str) -> float:
    return float(text.replace(",", ""))


def parse_date(text: str) -> str | None:
    """Normalize the date formats seen on real invoices to ISO. US slash order is assumed (MM/DD/YYYY)."""
    text = text.strip().rstrip(".,")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _find(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else None


_DATE = r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2} [A-Za-z]{3,9} \d{4}|[A-Za-z]{3,9} \d{1,2}, \d{4})"


def regex_extract(text: str) -> dict:
    out: dict = {}
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if first:
        out["vendor"] = first
    out["invoice_number"] = _find(r"invoice\s*(?:no\.?|number|#)\s*:?\s*([A-Z0-9][A-Z0-9-]+)", text)
    raw_date = _find(r"^(?:invoice\s+)?date\s*:?\s*" + _DATE, text) or _find(r"\bdate\s*:\s*" + _DATE, text)
    out["invoice_date"] = parse_date(raw_date) if raw_date else None
    raw_due = _find(r"\bdue(?:\s+date)?\s*:?\s*" + _DATE, text)
    out["due_date"] = parse_date(raw_due) if raw_due else None
    out["po_number"] = _find(r"(PO-\d+)", text)

    if re.search(r"\bEUR\b|€", text):
        out["currency"] = "EUR"
    elif re.search(r"\bGBP\b|£", text):
        out["currency"] = "GBP"
    elif re.search(r"\bUSD\b|\$", text):
        out["currency"] = "USD"

    sub = _find(r"^\s*sub\s*total\b[^0-9\n]*" + _AMOUNT, text)
    tax = _find(r"^\s*(?:sales\s+)?(?:tax|vat|gst)\b.*?" + _AMOUNT + r"\s*$", text)
    total = _find(r"^\s*(?:total(?:\s+due)?|amount\s+due)\b[^0-9\n]*" + _AMOUNT, text)
    out["subtotal"] = parse_amount(sub) if sub else None
    out["tax"] = parse_amount(tax) if tax else None
    out["total"] = parse_amount(total) if total else None

    items = []
    for m in re.finditer(r"^(?P<desc>[A-Za-z][^\n]*?)\s{2,}(?P<qty>\d+)\s+(?P<price>[0-9,]*\.\d{2})\s+"
                         r"(?P<amt>[0-9,]*\.\d{2})\s*$", text, re.MULTILINE):
        items.append({"description": m["desc"].strip(), "quantity": int(m["qty"]),
                      "unit_price": parse_amount(m["price"]), "amount": parse_amount(m["amt"])})
    out["line_items"] = items
    return {k: v for k, v in out.items() if v not in (None, "")}
