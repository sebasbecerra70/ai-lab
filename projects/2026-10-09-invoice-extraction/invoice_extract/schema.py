"""Invoice JSON schema (given to the LLM) and the business-rule validator applied to every extraction."""
from __future__ import annotations

import re
from datetime import date

INVOICE_SCHEMA = {
    "type": "object",
    "required": ["vendor", "invoice_number", "invoice_date", "currency", "total"],
    "properties": {
        "vendor": {"type": "string"},
        "invoice_number": {"type": "string"},
        "invoice_date": {"type": "string", "format": "date", "description": "ISO 8601, YYYY-MM-DD"},
        "due_date": {"type": "string", "format": "date"},
        "po_number": {"type": "string"},
        "currency": {"type": "string", "enum": ["USD", "EUR", "GBP", "CAD"]},
        "subtotal": {"type": "number"},
        "tax": {"type": "number"},
        "total": {"type": "number"},
        "line_items": {"type": "array", "items": {"type": "object", "properties": {
            "description": {"type": "string"}, "quantity": {"type": "number"},
            "unit_price": {"type": "number"}, "amount": {"type": "number"}}}},
    },
}
FIELDS = list(INVOICE_SCHEMA["properties"])
CURRENCIES = set(INVOICE_SCHEMA["properties"]["currency"]["enum"])
TOLERANCE = 0.011  # one cent plus float noise


def _iso(value) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def validate(inv: dict) -> dict[str, str]:
    """Return {field: problem}. Empty dict means the invoice is safe to post to AP."""
    errors: dict[str, str] = {}
    for f in INVOICE_SCHEMA["required"]:
        if inv.get(f) in (None, ""):
            errors[f] = "missing"
    for f in ("vendor", "invoice_number", "po_number"):
        if f in inv and inv[f] is not None and not isinstance(inv[f], str):
            errors[f] = "must be a string"
    for f in ("invoice_date", "due_date"):
        if inv.get(f) is not None and _iso(inv[f]) is None:
            errors[f] = "must be an ISO date YYYY-MM-DD"
    if inv.get("currency") is not None and inv["currency"] not in CURRENCIES:
        errors["currency"] = f"must be one of {sorted(CURRENCIES)}"
    for f in ("subtotal", "tax", "total"):
        if inv.get(f) is not None and not _num(inv[f]):
            errors[f] = "must be a non-negative number"
    if errors:
        return errors

    issued, due = _iso(inv["invoice_date"]), _iso(inv.get("due_date"))
    if due and due < issued:
        errors["due_date"] = "is before the invoice date"
    items = inv.get("line_items") or []
    for i, item in enumerate(items):
        if all(_num(item.get(k)) for k in ("quantity", "unit_price", "amount")):
            if abs(item["quantity"] * item["unit_price"] - item["amount"]) > TOLERANCE:
                errors["line_items"] = f"line {i + 1}: quantity × unit_price != amount"
        else:
            errors["line_items"] = f"line {i + 1}: quantity, unit_price and amount must be numbers"
    # Totals must reconcile: this catches the classic transposed-digit or dropped-line hallucination.
    if items and inv.get("subtotal") is not None and "line_items" not in errors:
        if abs(sum(it["amount"] for it in items) - inv["subtotal"]) > TOLERANCE:
            errors["subtotal"] = "does not equal the sum of line items"
    if inv.get("subtotal") is not None and inv.get("tax") is not None:
        if abs(inv["subtotal"] + inv["tax"] - inv["total"]) > TOLERANCE:
            errors["total"] = "does not equal subtotal + tax"
    return errors
