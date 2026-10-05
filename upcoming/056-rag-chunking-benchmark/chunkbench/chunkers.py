"""Three chunking strategies over markdown documents. Every chunk keeps its body text (what gets shown to the
model and checked for the answer) separately from its index text (what retrieval scores against)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Doc:
    name: str
    text: str


@dataclass(frozen=True)
class Chunk:
    doc: str
    text: str
    heading: str = ""

    @property
    def index_text(self) -> str:
        return f"{self.heading}\n{self.text}" if self.heading else self.text

    @property
    def words(self) -> int:
        return len(self.text.split())


def load_docs(folder: Path) -> list[Doc]:
    return [Doc(p.name, p.read_text()) for p in sorted(folder.glob("*.md"))]


def plain(markdown: str) -> str:
    """Markdown with heading lines removed, so fixed and sentence chunkers see only prose."""
    return "\n".join(ln for ln in markdown.splitlines() if not ln.startswith("#"))


def sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text).strip()
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", flat) if s]


def fixed(doc: Doc, size: int = 100, overlap: int | None = None) -> list[Chunk]:
    """Sliding window of `size` words with `overlap` (default 20% of size). Cheap and predictable, but blind
    to meaning: a window boundary can cut a sentence, or an answer, in half."""
    overlap = size // 5 if overlap is None else overlap
    if not 0 <= overlap < size:
        raise ValueError("overlap must be in [0, size)")
    words = plain(doc.text).split()
    step = size - overlap
    return [Chunk(doc.name, " ".join(words[i:i + size])) for i in range(0, max(len(words) - overlap, 1), step)]


def pack(doc: str, sents: list[str], size: int, heading: str = "") -> list[Chunk]:
    """Greedily pack whole sentences into chunks of at most `size` words (a longer sentence stands alone)."""
    out, cur = [], []
    for s in sents:
        if cur and len(" ".join(cur + [s]).split()) > size:
            out.append(Chunk(doc, " ".join(cur), heading))
            cur = []
        cur.append(s)
    if cur:
        out.append(Chunk(doc, " ".join(cur), heading))
    return out


def sentence(doc: Doc, size: int = 100) -> list[Chunk]:
    """Pack whole sentences across the document, ignoring section boundaries."""
    return pack(doc.name, sentences(plain(doc.text)), size)


def sections(markdown: str) -> list[tuple[list[str], str]]:
    """Split markdown into (heading path, body) pairs, e.g. (["Expense Policy", "Travel", "Hotels"], "...")."""
    path: list[str] = []
    out: list[tuple[list[str], list[str]]] = []
    for ln in markdown.splitlines():
        m = re.match(r"^(#+)\s+(.*)", ln)
        if m:
            level = len(m.group(1))
            path = path[:level - 1] + [m.group(2).strip()]
            out.append((list(path), []))
        elif out:
            out[-1][1].append(ln)
        elif ln.strip():
            out.append(([], [ln]))
    return [(p, "\n".join(body).strip()) for p, body in out if "\n".join(body).strip()]


def heading(doc: Doc, size: int = 100) -> list[Chunk]:
    """One chunk per section, split at sentence boundaries if longer than `size`. The heading path
    ("Expense Policy > Travel > Hotels") is added to the index text, so a question about hotels can find a
    section whose body never says 'hotel'."""
    out = []
    for path, body in sections(doc.text):
        out += pack(doc.name, sentences(body), size, " > ".join(path))
    return out


STRATEGIES = {"fixed": fixed, "sentence": sentence, "heading": heading}


def chunk_corpus(docs: list[Doc], strategy: str, size: int = 100) -> list[Chunk]:
    fn = STRATEGIES[strategy]
    return [c for d in docs for c in fn(d, size)]
