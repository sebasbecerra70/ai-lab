"""Parse runbooks into procedures (one per '## ' heading) and rank them with BM25."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

STOP = set("a an the and or of to in on for is are be it its this that with by at as do does i we my our what how when should if then from".split())
STEP = re.compile(r"^(\d+)\.\s+(.*)$")


def tokenize(text: str) -> list[str]:
    toks = [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]
    # light stemming so "tripped"/"trips"/"trip" collide
    return [re.sub(r"(ing|ed|es|s)$", "", t) if len(t) > 4 else t for t in toks]


def terms(text: str) -> list[str]:
    """Unigrams plus raw bigrams. Bigrams keep stopwords so "on battery" can tell
    "UPS on battery" apart from "UPS battery string"."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return tokenize(text) + [f"{a}_{b}" for a, b in zip(words, words[1:])]


@dataclass
class Procedure:
    doc: str          # file stem, e.g. "power_distribution"
    title: str        # section heading, e.g. "PDU breaker trip"
    steps: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.doc}#{re.sub(r'[^a-z0-9]+', '-', self.title.lower()).strip('-')}"

    def step_id(self, n: int) -> str:
        return f"{self.id}:{n}"

    def text(self) -> str:
        return self.title + " " + " ".join(self.steps)


def load_runbooks(folder: Path) -> list[Procedure]:
    procs: list[Procedure] = []
    for path in sorted(folder.glob("*.md")):
        current = None
        for line in path.read_text().splitlines():
            if line.startswith("## "):
                current = Procedure(path.stem, line[3:].strip())
                procs.append(current)
            elif current and (m := STEP.match(line.strip())):
                current.steps.append(m.group(2))
    return procs


class BM25:
    def __init__(self, procs: list[Procedure], k1: float = 1.4, b: float = 0.75):
        self.procs, self.k1, self.b = procs, k1, b
        # title tokens count twice: headings are the most specific signal in a runbook
        self.docs = [Counter(terms(p.text()) + terms(p.title)) for p in procs]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lens) / max(len(self.lens), 1)
        df = Counter(t for d in self.docs for t in d)
        n = len(procs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def score(self, query: str, i: int) -> float:
        d, s = self.docs[i], 0.0
        for t in set(terms(query)):
            if t in d:
                tf = d[t]
                s += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg))
        return s

    def matched_terms(self, query: str, i: int) -> int:
        return len(set(tokenize(query)) & set(self.docs[i]))

    def search(self, query: str, k: int = 2, min_terms: int = 1) -> list[tuple[Procedure, float]]:
        """Top-k procedures; `min_terms` drops matches that share fewer distinct query terms than that."""
        scored = [(p, self.score(query, i)) for i, p in enumerate(self.procs) if self.matched_terms(query, i) >= min_terms]
        ranked = sorted(scored, key=lambda x: -x[1])
        return [(p, s) for p, s in ranked[:k] if s > 0]
