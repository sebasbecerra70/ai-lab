"""Q&A-pair chunking and BM25 retrieval over past proposals, plus a coverage-based confidence score."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_TOKEN = re.compile(r"[a-z0-9]+")
# Generic English plus RFP boilerplate ("please describe your ...") that carries no topic signal.
_STOP = frozenset("""
a an the and or of to in on for is are be by with at as it this that from do does you your we our us what which
how long when where who can please describe list provide explain any all have has will would should there their
""".split())
# Buyer vocabulary -> the words our proposals use. Cheap, reviewable, and it fixes most misses.
_SYNONYMS = {"sso": "sign", "encrypted": "encryption", "warehouse": "site", "facility": "site"}


def _stem(t: str) -> str:
    return t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith(("ss", "us")) else t


def tokenize(text: str) -> list[str]:
    out = []
    for t in _TOKEN.findall(text.lower()):
        if len(t) < 2 or t in _STOP:
            continue
        t = _stem(t)
        out.append(_SYNONYMS.get(t, t))
    return out


@dataclass(frozen=True)
class Passage:
    source: str
    question: str
    answer: str

    @property
    def text(self) -> str:
        return f"{self.question}\n{self.answer}"


def load_passages(directory: str | Path) -> list[Passage]:
    """One passage per '## Q:' section: answers are reused at the question level, so cite at that level."""
    passages = []
    for f in sorted(Path(directory).glob("*.md")):
        for block in re.split(r"\n(?=## Q:)", f.read_text()):
            if not block.startswith("## Q:"):
                continue
            head, _, body = block.partition("\n")
            passages.append(Passage(f.name, head[len("## Q:"):].strip(), body.strip()))
    if not passages:
        raise ValueError(f"no '## Q:' sections found in {directory}")
    return passages


class BM25:
    def __init__(self, passages: list[Passage], k1: float = 1.5, b: float = 0.75):
        self.passages, self.k1, self.b = passages, k1, b
        self.docs = [Counter(tokenize(p.text)) for p in passages]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = sum(self.lengths) / len(self.lengths)
        df = Counter(t for d in self.docs for t in d)
        n = len(passages)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query_terms: list[str], i: int) -> float:
        d, length, s = self.docs[i], self.lengths[i], 0.0
        for t in query_terms:
            tf = d.get(t, 0)
            if tf:
                s += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg_len))
        return s

    def coverage(self, query_terms: list[str], i: int) -> float:
        """IDF-weighted share of query terms present in the passage, in [0, 1].

        BM25 scores aren't comparable across queries, so they make a poor threshold. Coverage is: 0.8 means
        the passage contains the terms that carry 80% of the question's information.
        """
        # Terms the corpus never uses get a median weight: they may be topic words (FedRAMP) or filler (miss).
        known = sorted(self.idf.values())
        unknown_idf = known[len(known) // 2] if known else 1.0
        weights = {t: self.idf.get(t, unknown_idf) for t in set(query_terms)}
        total = sum(weights.values())
        return sum(w for t, w in weights.items() if t in self.docs[i]) / total if total else 0.0

    def search(self, query: str, k: int = 3) -> list[tuple[Passage, float, float]]:
        terms = tokenize(query)
        hits = [(p, self.score(terms, i), self.coverage(terms, i)) for i, p in enumerate(self.passages)]
        hits = [h for h in hits if h[1] > 0]
        hits.sort(key=lambda h: -h[1])
        return hits[:k]
