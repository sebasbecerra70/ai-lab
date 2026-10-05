"""Parse a call transcript: deal header, speaker turns, and which speakers are on the customer side."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Turn:
    speaker: str
    text: str
    is_seller: bool


@dataclass
class Call:
    name: str
    deal: str
    stage: str
    amount: float
    turns: list[Turn] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(f"{t.speaker}: {t.text}" for t in self.turns)

    @property
    def customer_speakers(self) -> list[str]:
        return sorted({t.speaker for t in self.turns if not t.is_seller})


def load(path: Path) -> Call:
    lines = path.read_text().splitlines()
    m = re.match(r"DEAL: (.+?) \| stage: (\w+) \| amount: (\d+)", lines[0])
    call = Call(path.stem, m.group(1), m.group(2), float(m.group(3)))
    seller = None
    for ln in lines[1:]:
        sm = re.match(r"^(AE \()?([A-Z][\w]+)(?:\)| \([^)]*\))?: (.+)$", ln)
        if not sm:
            continue
        if sm.group(1):
            seller = sm.group(2)
        name = sm.group(2)
        call.turns.append(Turn(name, sm.group(3), name == seller))
    return call


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%$]", " ", s.lower())).strip()


def quote_in(call: Call, quote: str) -> bool:
    """Evidence must be a verbatim (punctuation-insensitive) span of something the customer said."""
    q = normalize(quote)
    return bool(q) and any(q in normalize(t.text) for t in call.turns if not t.is_seller)
