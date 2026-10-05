"""PII detection and reversible redaction. The model sees placeholders; the vault can restore them for authorized output."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PII_PATTERNS = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b")),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]


def luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        checksum += d
    return len(digits) >= 13 and checksum % 10 == 0


@dataclass
class Vault:
    """Maps placeholders like [EMAIL_1] back to the original values; same value -> same placeholder."""
    values: dict[str, str] = field(default_factory=dict)

    def token_for(self, kind: str, value: str) -> str:
        for tok, v in self.values.items():
            if v == value and tok.startswith(f"[{kind}_"):
                return tok
        tok = f"[{kind}_{sum(t.startswith(f'[{kind}_') for t in self.values) + 1}]"
        self.values[tok] = value
        return tok

    def restore(self, text: str) -> str:
        for tok, v in self.values.items():
            text = text.replace(tok, v)
        return text


def redact(text: str, vault: Vault | None = None) -> tuple[str, Vault, list[str]]:
    vault = vault or Vault()
    found = []
    for kind, rx in PII_PATTERNS:
        def sub(m: re.Match, kind=kind) -> str:
            value = m.group(0)
            if kind == "CARD" and not luhn_ok(value):
                return value  # order numbers and the like: long digit runs that fail Luhn are not cards
            found.append(kind)
            return vault.token_for(kind, value)
        text = rx.sub(sub, text)
    return text, vault, found
