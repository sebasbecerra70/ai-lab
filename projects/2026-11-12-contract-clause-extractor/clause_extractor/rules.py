"""Clause segmentation, rule-based classification, and field extraction."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CLAUSE_TYPES = ["renewal", "termination", "liability", "indemnification", "payment",
                "confidentiality", "governing_law", "other"]

# Ordered: the first matching type wins, so specific patterns come before broad ones.
TYPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("renewal", re.compile(r"\b(renew|renewal|initial term)\b", re.I)),
    ("liability", re.compile(r"\b(limitation of liability|liability shall|aggregate liability|total liability|no liability)\b", re.I)),
    ("indemnification", re.compile(r"\bindemni", re.I)),
    ("termination", re.compile(r"\bterminat", re.I)),
    ("payment", re.compile(r"\b(invoice|payout|pay |fees?\b|commission)", re.I)),
    ("confidentiality", re.compile(r"\bconfidential", re.I)),
    ("governing_law", re.compile(r"\bgoverned by the laws\b", re.I)),
]


@dataclass
class Clause:
    number: int
    heading: str
    text: str
    type: str = "other"
    fields: dict = field(default_factory=dict)
    source: str = "rules"  # rules | llm


def our_role(contract_text: str) -> str:
    """Contracts name us as 'Our Company ("Role")'; risk is judged from that party's side."""
    m = re.search(r'Our Company \("(\w+)"\)', contract_text)
    return m.group(1) if m else "Our Company"


def split_clauses(text: str) -> list[Clause]:
    clauses = []
    for m in re.finditer(r"^(\d+)\.\s+([^.\n]+)\.\s+(.+?)(?=^\d+\.\s|\Z)", text, re.M | re.S):
        clauses.append(Clause(int(m.group(1)), m.group(2).strip(), " ".join(m.group(3).split())))
    return clauses


def classify(clause: Clause) -> str:
    haystack = f"{clause.heading}. {clause.text}"
    # A heading is the strongest signal; fall back to the body.
    for ctype, pat in TYPE_PATTERNS:
        if pat.search(clause.heading):
            return ctype
    for ctype, pat in TYPE_PATTERNS:
        if pat.search(haystack):
            return ctype
    return "other"


def _num(s: str) -> int | None:
    """Pull the digits from 'ninety (90)' or '90'."""
    m = re.search(r"\((\d+)\)", s) or re.search(r"\b(\d+)\b", s)
    return int(m.group(1)) if m else None


_PERIOD = r"((?:\w+[- ])?\(?\d+\)?)\s*[- ]?\s*(year|month|day)s?"


def _months(qty: int, unit: str) -> int:
    return qty * {"year": 12, "month": 1, "day": 0}[unit.lower()]


def extract_fields(ctype: str, text: str, role: str) -> dict:
    t = text
    if ctype == "renewal":
        auto = bool(re.search(r"automatically renew", t, re.I))
        out: dict = {"auto_renew": auto}
        m = re.search(r"successive\s+" + _PERIOD, t, re.I)
        if m:
            out["renewal_months"] = _months(_num(m.group(1)) or 0, m.group(2))
        m = re.search(r"(?:at least\s+)?" + r"((?:[\w-]+ )+?\(\d+\)|\d+)\s+days\s+before", t, re.I)
        if m:
            out["notice_days"] = _num(m.group(1))
        return out
    if ctype == "termination":
        parties = re.findall(r"(Either|\w+)(?: party)? may (?:suspend or )?terminate (?:this Agreement |these Terms |\w+'s listing )?(?:for convenience|at any time)", t, re.I)
        out = {"convenience_parties": sorted({p.lower() for p in parties})}
        m = re.search(r"convenience (?:up)?on\s+((?:[\w-]+ )*?\(\d+\)|\d+)\s+days", t, re.I)
        if m:
            out["notice_days"] = _num(m.group(1))
        out["any_time"] = bool(re.search(r"at any time|sole discretion", t, re.I))
        return out
    if ctype == "liability":
        out = {}
        m = re.search(r"(?:fees paid[^.]*?)(?:in the|preceding)?\s*((?:[\w-]+ )?\(\d+\))\s*(month|year)s?", t, re.I)
        if m:
            out["cap_months"] = _months(_num(m.group(1)) or 0, m.group(2))
        unlimited = re.findall(r"(\w+)'s liability (?:shall be unlimited|[^.]*?shall not be limited)", t, re.I)
        out["uncapped_parties"] = sorted({u.lower() for u in unlimited})
        out["we_are_uncapped"] = role.lower() in out["uncapped_parties"]
        return out
    if ctype == "indemnification":
        mutual = bool(re.search(r"\b(mutual|each party shall indemnify)\b", t, re.I))
        m = re.match(r"\s*(\w+) shall (?:defend and )?indemnify", t, re.I)
        return {"mutual": mutual, "indemnitor": "each" if mutual else (m.group(1).lower() if m else "unknown"),
                "broad_scope": bool(re.search(r"all claims|of any kind|any third-party claim arising", t, re.I))}
    if ctype == "payment":
        m = re.search(r"(?:net\s+)?((?:[\w-]+ )?\(\d+\)|\d+)\s+days", t, re.I)
        payer = re.search(r"(\w+) shall pay", t)
        payee = re.search(r"[Pp]ayouts to (\w+)", t)
        return {"days": _num(m.group(1)) if m else None,
                "we_are_payee": bool(payee and payee.group(1).lower() == role.lower())
                or bool(payer and payer.group(1).lower() != role.lower())}
    if ctype == "confidentiality":
        m = re.search(_PERIOD, t, re.I)
        return {"survival_months": _months(_num(m.group(1)) or 0, m.group(2)) if m else None}
    if ctype == "governing_law":
        m = re.search(r"laws of (?:the )?(State of )?([A-Z][\w ]+?)(?:,|\.|$)", t)
        return {"jurisdiction": m.group(2).strip() if m else None}
    return {}
