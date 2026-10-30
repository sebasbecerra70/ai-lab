"""Hybrid retrieval: fuse BM25 and dense rankings, plus the eval metrics used to compare them."""
from __future__ import annotations

import json
from pathlib import Path

from .bm25 import BM25
from .embed import HashingEmbedder
from .index import VectorIndex


def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: score = Σ 1/(k + rank). Uses ranks only, so BM25's unbounded scores and
    cosine's [-1, 1] never need to be put on one scale."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda t: (-t[1], t[0]))


class SearchEngine:
    def __init__(self, docs: list[dict], dim: int = 1024, depth: int = 20):
        self.docs = {d["id"]: d for d in docs}
        self.depth = depth  # how deep each retriever's list goes into the fusion
        texts = [(d["id"], f"{d['title']}. {d['text']}") for d in docs]
        self.bm25 = BM25().fit(texts)
        self.embedder = HashingEmbedder(dim).fit([t for _, t in texts])
        self.index = VectorIndex(dim)
        for doc_id, text in texts:
            self.index.add(doc_id, self.embedder.embed(text))

    def search(self, query: str, mode: str = "hybrid", k: int = 5) -> list[tuple[str, float]]:
        if mode == "bm25":
            return self.bm25.search(query, k)
        dense = self.index.search(self.embedder.embed(query), self.depth)
        if mode == "dense":
            return dense[:k]
        if mode == "hybrid":
            lexical = self.bm25.search(query, self.depth)
            return rrf([[d for d, _ in lexical], [d for d, _ in dense]])[:k]
        raise ValueError(f"unknown mode {mode!r}")


def load_docs(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def evaluate(engine: SearchEngine, queries: list[dict], mode: str, k: int = 3) -> dict[str, float]:
    """recall@k: share of queries with a relevant doc in the top k. MRR: mean of 1 / rank of the first hit."""
    hits, rr = 0, 0.0
    for q in queries:
        ranked = [d for d, _ in engine.search(q["q"], mode, k=10)]
        first = next((i for i, d in enumerate(ranked, 1) if d in q["relevant"]), None)
        hits += first is not None and first <= k
        rr += 1 / first if first else 0.0
    return {f"recall@{k}": hits / len(queries), "mrr": rr / len(queries)}
