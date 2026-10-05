"""Dependency-free TF-IDF retriever with cosine similarity."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an the and or of to in on for is are be by with at as it this that from must should when if what how do i who why".split()
)


def tokenize(text: str) -> list[str]:
    # Single characters (e.g. the "s" left from "driver's") add noise, not signal.
    return [t for t in _TOKEN.findall(text.lower()) if len(t) > 1 and t not in _STOP]


@dataclass(frozen=True)
class Chunk:
    source: str
    text: str


def chunk_markdown(source: str, text: str) -> list[Chunk]:
    """Split a markdown SOP into one chunk per section (## heading)."""
    sections = re.split(r"\n(?=#{1,3} )", text.strip())
    return [Chunk(source, s.strip()) for s in sections if s.strip()]


class TfidfRetriever:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise ValueError("retriever needs at least one chunk")
        self.chunks = chunks
        docs = [Counter(tokenize(c.text)) for c in chunks]
        df = Counter(term for d in docs for term in d)
        n = len(chunks)
        # Smoothed IDF so terms appearing everywhere still get a small weight.
        self.idf = {t: math.log((1 + n) / (1 + f)) + 1 for t, f in df.items()}
        self.vectors = [self._weigh(d) for d in docs]

    @classmethod
    def from_directory(cls, path: str | Path) -> "TfidfRetriever":
        chunks: list[Chunk] = []
        for f in sorted(Path(path).glob("*.md")):
            chunks.extend(chunk_markdown(f.name, f.read_text()))
        return cls(chunks)

    def _weigh(self, counts: Counter) -> dict[str, float]:
        vec = {t: c * self.idf.get(t, 0.0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def search(self, query: str, k: int = 3) -> list[tuple[Chunk, float]]:
        q = self._weigh(Counter(tokenize(query)))
        scored = [
            (chunk, sum(w * vec.get(t, 0.0) for t, w in q.items()))
            for chunk, vec in zip(self.chunks, self.vectors)
        ]
        scored = [s for s in scored if s[1] > 0]
        scored.sort(key=lambda s: s[1], reverse=True)
        return scored[:k]
