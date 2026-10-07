"""Load requests, cluster them, label each cluster with an LLM, and rank themes by revenue at stake."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .kmeans import choose_k, kmeans
from .llm import LLMClient
from .vectorize import TfidfVectorizer, Vector, cosine

LABEL_SYSTEM = (
    "You name product themes for a roadmap review. Reply with a short theme name of 2-6 words, "
    "no punctuation at the end, nothing else."
)


@dataclass(frozen=True)
class Request:
    id: int
    account: str
    arr_usd: float
    text: str


@dataclass
class Theme:
    label: str
    requests: list[Request]
    top_terms: list[str]

    @property
    def accounts(self) -> set[str]:
        return {r.account for r in self.requests}

    @property
    def arr_at_stake(self) -> float:
        # Count each account once: three asks from one customer are not three times the revenue.
        seen: dict[str, float] = {}
        for r in self.requests:
            seen[r.account] = r.arr_usd
        return sum(seen.values())


def load_requests(path: str | Path) -> list[Request]:
    with open(path, newline="") as f:
        return [Request(int(r["id"]), r["account"], float(r["arr_usd"]), r["text"]) for r in csv.DictReader(f)]


def top_terms(centroid: Vector, n: int = 5) -> list[str]:
    return [t for t, _ in sorted(centroid.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def label_prompt(terms: list[str], examples: list[Request]) -> str:
    lines = "\n".join(f"- {r.text}" for r in examples)
    return f"Top terms: {', '.join(terms)}\nRepresentative requests:\n{lines}\n\nTheme name:"


def cluster_requests(requests: list[Request], llm: LLMClient, k: int | None = None,
                     k_range: range = range(4, 8), seed: int = 7) -> tuple[list[Theme], dict[int, float]]:
    vectors = TfidfVectorizer(min_df=2).fit_transform([r.text for r in requests])
    scores: dict[int, float] = {}
    if k is None:
        k, scores = choose_k(vectors, k_range, seed)
    result = kmeans(vectors, k, seed)
    themes = []
    for j, centroid in enumerate(result.centroids):
        members = [(r, v) for r, v, lab in zip(requests, vectors, result.labels) if lab == j]
        if not members:
            continue
        # Show the model the requests closest to the centroid; they are the most typical ones.
        members.sort(key=lambda rv: -cosine(rv[1], centroid))
        terms = top_terms(centroid)
        label = llm.complete(LABEL_SYSTEM, label_prompt(terms, [r for r, _ in members[:4]]))
        themes.append(Theme(label, [r for r, _ in members], terms))
    themes.sort(key=lambda t: (-t.arr_at_stake, t.label))
    return themes, scores


def render(themes: list[Theme], scores: dict[int, float]) -> str:
    lines = []
    if scores:
        best = max(scores, key=scores.get)
        lines.append("silhouette by k: " + "  ".join(f"k={k}:{s:.2f}" for k, s in scores.items()) + f"  -> k={best}")
    for i, t in enumerate(themes, 1):
        lines.append(f"{i}. {t.label}  [{len(t.requests)} requests, {len(t.accounts)} accounts, "
                     f"${t.arr_at_stake / 1000:,.0f}k ARR]")
        lines.append(f"   terms: {', '.join(t.top_terms)}")
        lines.append(f"   e.g. \"{t.requests[0].text}\"")
    return "\n".join(lines)
