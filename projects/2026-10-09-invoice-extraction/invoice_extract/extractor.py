"""LLM-first extraction with schema validation and field-level regex fallback."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .llm import LLMClient
from .regex_fallback import parse_date, regex_extract
from .schema import FIELDS, INVOICE_SCHEMA, validate

SYSTEM = (
    "You extract accounts-payable data from invoice text. Return ONLY a JSON object matching this "
    "JSON schema, with dates as YYYY-MM-DD and amounts as numbers without currency symbols. "
    "Omit fields that are not on the invoice; never guess.\n" + json.dumps(INVOICE_SCHEMA)
)


@dataclass
class Extraction:
    data: dict
    sources: dict[str, str]          # field -> "llm" | "regex"
    errors: dict[str, str]           # remaining validation problems
    llm_errors: dict[str, str] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "ok" if not self.errors else "needs_review"


def parse_json_object(text: str) -> dict | None:
    """Pull the first JSON object out of a model reply, tolerating code fences and preambles."""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
                return obj if isinstance(obj, dict) else None
    return None  # truncated reply


def _coerce(data: dict) -> dict:
    """Cheap, safe repairs before validating: normalize date formats the model left un-normalized."""
    out = dict(data)
    for f in ("invoice_date", "due_date"):
        if isinstance(out.get(f), str):
            out[f] = parse_date(out[f]) or out[f]
    return out


class InvoiceExtractor:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def extract(self, text: str) -> Extraction:
        fallback = regex_extract(text)
        parsed = parse_json_object(self.llm.complete(SYSTEM, text))
        if parsed is None:
            return Extraction(fallback, {k: "regex" for k in fallback}, validate(fallback), {"_": "unparseable"})

        data = _coerce({k: v for k, v in parsed.items() if k in FIELDS})
        sources = {k: "llm" for k in data}
        llm_errors = validate(data)
        # Replace only the fields that failed, and only with a value regex actually found.
        # A reconciliation error on `total` may really be a bad subtotal, so try both.
        suspect = set(llm_errors) | ({"subtotal", "tax"} if "total" in llm_errors else set())
        for f in FIELDS:
            missing = f not in data and f in fallback
            if (f in suspect or missing) and f in fallback and fallback[f] != data.get(f):
                data[f] = fallback[f]
                sources[f] = "regex"
        return Extraction(data, sources, validate(data), llm_errors)
