"""Spherical k-means (cosine) over sparse vectors, with k-means++ seeding and silhouette scoring."""
from __future__ import annotations

import random
from dataclasses import dataclass

from .vectorize import Vector, cosine, normalize


@dataclass
class KMeansResult:
    labels: list[int]
    centroids: list[Vector]
    inertia: float  # sum of (1 - cosine) to the assigned centroid; lower is tighter


def _mean(vectors: list[Vector]) -> Vector:
    acc: dict[str, float] = {}
    for v in vectors:
        for k, x in v.items():
            acc[k] = acc.get(k, 0.0) + x
    return normalize(acc)


def _seed(vectors: list[Vector], k: int, rng: random.Random) -> list[Vector]:
    """k-means++: pick each new centroid with probability proportional to its distance from existing ones."""
    centroids = [vectors[rng.randrange(len(vectors))]]
    while len(centroids) < k:
        d = [min(1 - cosine(v, c) for c in centroids) for v in vectors]
        total = sum(d)
        if total <= 0:
            centroids.append(vectors[rng.randrange(len(vectors))])
            continue
        r, acc = rng.random() * total, 0.0
        for v, dist in zip(vectors, d):
            acc += dist
            if acc >= r:
                centroids.append(v)
                break
    return centroids


def _run(vectors: list[Vector], k: int, rng: random.Random, max_iter: int) -> KMeansResult:
    centroids = _seed(vectors, k, rng)
    labels = [-1] * len(vectors)
    for _ in range(max_iter):
        new = [max(range(k), key=lambda j: cosine(v, centroids[j])) for v in vectors]
        if new == labels:
            break
        labels = new
        for j in range(k):
            members = [v for v, lab in zip(vectors, labels) if lab == j]
            if members:  # an empty cluster keeps its old centroid rather than collapsing
                centroids[j] = _mean(members)
    inertia = sum(1 - cosine(v, centroids[lab]) for v, lab in zip(vectors, labels))
    return KMeansResult(labels, centroids, inertia)


def kmeans(vectors: list[Vector], k: int, seed: int = 7, n_init: int = 8, max_iter: int = 50) -> KMeansResult:
    if not 1 <= k <= len(vectors):
        raise ValueError(f"k must be between 1 and {len(vectors)}")
    rng = random.Random(seed)
    # Several restarts and keep the tightest: k-means only finds a local optimum.
    return min((_run(vectors, k, rng, max_iter) for _ in range(n_init)), key=lambda r: r.inertia)


def silhouette(vectors: list[Vector], labels: list[int]) -> float:
    """Mean silhouette with cosine distance. Near 1 = well separated, near 0 = overlapping."""
    clusters = set(labels)
    if len(clusters) < 2:
        return 0.0
    scores = []
    for i, v in enumerate(vectors):
        dist: dict[int, list[float]] = {}
        for j, w in enumerate(vectors):
            if i != j:
                dist.setdefault(labels[j], []).append(1 - cosine(v, w))
        own = dist.get(labels[i])
        if not own:
            scores.append(0.0)
            continue
        a = sum(own) / len(own)
        b = min(sum(d) / len(d) for c, d in dist.items() if c != labels[i])
        scores.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return sum(scores) / len(scores)


def choose_k(vectors: list[Vector], k_range: range, seed: int = 7) -> tuple[int, dict[int, float]]:
    scores = {k: silhouette(vectors, kmeans(vectors, k, seed).labels) for k in k_range}
    return max(scores, key=scores.get), scores
