"""Local research tools over Markdown company profiles. Every result carries a citation ref: '<doc>#<Section>'."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

WORD = re.compile(r"[a-z0-9]+")
STOP = set("a an the and or of to in on for is are was were be by with from at as its it this that which".split())


def tokenize(text: str) -> list[str]:
    return [w for w in WORD.findall(text.lower()) if w not in STOP]


@dataclass(frozen=True)
class Section:
    doc: str
    heading: str
    text: str

    @property
    def ref(self) -> str:
        return f"{self.doc}#{self.heading}"


class DocStore:
    def __init__(self, sections: list[Section], titles: dict[str, str]):
        self.sections = sections
        self.titles = titles
        self._tf = [Counter(tokenize(s.heading + " " + s.text)) for s in sections]
        self._len = [sum(tf.values()) for tf in self._tf]
        df = Counter(t for tf in self._tf for t in tf)
        n = len(sections)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._avg = sum(self._len) / max(1, n)

    @classmethod
    def from_dir(cls, root: Path) -> "DocStore":
        sections, titles = [], {}
        for path in sorted(list(root.glob("*.md")) + list((root / "companies").glob("*.md"))):
            doc, heading, buf = path.stem, None, []
            for line in path.read_text().splitlines():
                if line.startswith("# "):
                    titles[doc] = line[2:].strip()
                elif line.startswith("## "):
                    if heading:
                        sections.append(Section(doc, heading, "\n".join(buf).strip()))
                    heading, buf = line[3:].strip(), []
                elif heading:
                    buf.append(line)
            if heading:
                sections.append(Section(doc, heading, "\n".join(buf).strip()))
        return cls(sections, titles)

    def get(self, doc: str, heading: str) -> Section:
        for s in self.sections:
            if s.doc == doc and s.heading.lower() == heading.lower():
                return s
        available = [s.heading for s in self.sections if s.doc == doc]
        if not available:
            raise KeyError(f"unknown document '{doc}'")
        raise KeyError(f"no section '{heading}' in {doc}; available: {', '.join(available)}")

    def search(self, query: str, doc: str | None = None, k: int = 3, k1: float = 1.5, b: float = 0.75) -> list[tuple[Section, float]]:
        q = tokenize(query)
        scored = []
        for i, s in enumerate(self.sections):
            if doc and s.doc != doc:
                continue
            tf, length = self._tf[i], self._len[i]
            score = sum(self._idf.get(t, 0) * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * length / self._avg)) for t in q if t in tf)
            if score > 0:
                scored.append((s, round(score, 3)))
        return sorted(scored, key=lambda x: -x[1])[:k]


# ---- signal extraction and ICP fit ---------------------------------------------------------------

SIGNALS = [
    ("locations", re.compile(r"(\d[\d,]*)\s+(?:stores|locations|plants|processing plants|pharmacies|regional DCs)", re.I)),
    ("revenue", re.compile(r"[Rr]evenue (?:was )?\$([\d.]+)\s*(B|M)")),
    ("inventory", re.compile(r"[Ii]nventory(?: on the balance sheet)?(?: of)? (?:was |is )?\$([\d.]+)\s*(B|M)")),
    ("skus", re.compile(r"([\d,]+)\s+SKUs|about ([\d,]+)\)", re.I)),
    ("new_dc", re.compile(r"new [\d,]+ sq ft distribution center|new (?:\w+ )?(?:DC|distribution center)", re.I)),
    ("system_change", re.compile(r"(?:replace|migrat\w+|evaluating)[^.]*\b(ERP|S/4HANA|WMS|merchandising system)", re.I)),
    ("stockout_pain", re.compile(r"stockouts?[^.]*", re.I)),
]


def _money(num: str, unit: str) -> float:
    return float(num) * (1e9 if unit == "B" else 1e6)


def extract_signals(store: DocStore, doc: str) -> list[dict]:
    out = []
    for s in (x for x in store.sections if x.doc == doc):
        for name, rx in SIGNALS:
            for m in rx.finditer(s.text):
                if name in ("revenue", "inventory"):
                    value: object = _money(m.group(1), m.group(2))
                elif name in ("locations", "skus"):
                    value = int((m.group(1) or m.group(2) or "0").replace(",", ""))
                else:
                    value = m.group(0).strip()
                out.append({"signal": name, "value": value, "ref": s.ref})
    return out


def _display(v: object) -> str:
    if isinstance(v, float):
        return f"${v / 1e9:.1f}B" if v >= 1e9 else f"${v / 1e6:.0f}M"
    return f"{v:,}" if isinstance(v, int) else str(v)


def score_fit(store: DocStore, doc: str) -> dict:
    """Score the account against the ideal customer profile in our_product.md (4 criteria, 1 point each)."""
    sig: dict[str, list[dict]] = {}
    for x in extract_signals(store, doc):
        sig.setdefault(x["signal"], []).append(x)
    first = lambda k: sig[k][0] if k in sig else None  # noqa: E731
    checks = [
        ("50+ locations", first("locations"), lambda v: v >= 50),
        ("10k+ SKUs", first("skus"), lambda v: v >= 10_000),
        ("inventory above $50M", first("inventory"), lambda v: v > 50e6),
        ("ERP/WMS change or new DC in flight", first("system_change") or first("new_dc"), lambda v: True),
    ]
    reasons, score = [], 0
    for label, hit, ok in checks:
        passed = bool(hit) and ok(hit["value"])
        score += passed
        reasons.append({"criterion": label, "met": passed, "evidence": _display(hit["value"]) if hit else None, "ref": hit["ref"] if hit else None})
    return {"score": score, "max": len(checks), "reasons": reasons}
