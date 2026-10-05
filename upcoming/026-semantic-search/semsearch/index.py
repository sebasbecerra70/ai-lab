"""A tiny vector index: exact cosine search, plus an IVF (cluster-and-probe) path for when a scan gets too slow."""
from __future__ import annotations

import random

from .embed import Vector, cosine


def _normalize(v: Vector) -> Vector:
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v] if n else v


class VectorIndex:
    """Stores unit vectors. search() scans everything; search_ivf() only scores the nearest clusters.

    IVF, as in FAISS's IndexIVFFlat: spherical k-means splits the docs into `nlist` clusters, and a query
    is compared with the centroids first, then only with docs in its `nprobe` closest clusters. That keeps
    recall high even when query-doc similarities are low (short queries against longer articles), which is
    where random-hyperplane LSH falls apart. With 30 docs a scan is instant; the IVF path shows the
    recall-vs-work trade-off you would tune at a million docs.
    """

    def __init__(self, dim: int, nlist: int = 6, nprobe: int = 2, seed: int = 7):
        self.dim, self.nlist, self.nprobe, self.seed = dim, nlist, nprobe, seed
        self.ids: list[str] = []
        self.vectors: list[Vector] = []
        self.centroids: list[Vector] = []
        self.lists: list[list[int]] = []

    def add(self, doc_id: str, v: Vector) -> None:
        if len(v) != self.dim:
            raise ValueError(f"expected dim {self.dim}, got {len(v)}")
        if doc_id in self.ids:
            raise ValueError(f"duplicate id {doc_id}")
        self.ids.append(doc_id)
        self.vectors.append(v)
        self.centroids = []  # clusters are stale until the next train()

    def __len__(self) -> int:
        return len(self.ids)

    def train(self, iters: int = 10) -> None:
        """Spherical k-means: assign by cosine to the nearest centroid, recompute centroids as normalized means."""
        k = min(self.nlist, len(self.vectors))
        rng = random.Random(self.seed)
        self.centroids = [list(self.vectors[i]) for i in rng.sample(range(len(self.vectors)), k)]
        for _ in range(iters):
            self.lists = [[] for _ in range(k)]
            for i, v in enumerate(self.vectors):
                self.lists[max(range(k), key=lambda c: cosine(v, self.centroids[c]))].append(i)
            for c, members in enumerate(self.lists):
                if members:  # an empty cluster keeps its old centroid
                    self.centroids[c] = _normalize([sum(col) for col in zip(*(self.vectors[i] for i in members))])

    def search(self, q: Vector, k: int = 5) -> list[tuple[str, float]]:
        scored = [(self.ids[i], cosine(q, v)) for i, v in enumerate(self.vectors)]
        return sorted(scored, key=lambda t: (-t[1], t[0]))[:k]

    def candidates(self, q: Vector) -> set[int]:
        if not self.centroids:
            self.train()
        nearest = sorted(range(len(self.centroids)), key=lambda c: -cosine(q, self.centroids[c]))[:self.nprobe]
        return {i for c in nearest for i in self.lists[c]}

    def search_ivf(self, q: Vector, k: int = 5) -> list[tuple[str, float]]:
        scored = [(self.ids[i], cosine(q, self.vectors[i])) for i in self.candidates(q)]
        return sorted(scored, key=lambda t: (-t[1], t[0]))[:k]
