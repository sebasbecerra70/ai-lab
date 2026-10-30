"""Hashed n-gram embeddings: the 'hashing trick' turns words, word pairs and character n-grams into a
fixed-size dense vector with no vocabulary and no training beyond an IDF pass over the corpus.

Character n-grams are what make it semantic-ish: 'passwrd' and 'password' share most of their subwords,
and 'encrypting' lands near 'encrypt'. It will not know that 'maternity' means 'parental'; that needs a
learned model, which is the main trade-off for being dependency-free and fully deterministic.
"""
from __future__ import annotations

import hashlib
import math

from .text import char_ngrams, tokens

Vector = list[float]


def _bucket(feature: str, dim: int) -> tuple[int, float]:
    """Stable hash -> (index, sign). The sign hash keeps collisions from all adding up in one direction."""
    h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
    return h % dim, 1.0 if (h >> 63) & 1 else -1.0


def cosine(a: Vector, b: Vector) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class HashingEmbedder:
    def __init__(self, dim: int = 1024, word_weight: float = 1.0, bigram_weight: float = 0.3,
                 char_weight: float = 1.0):
        self.dim = dim
        self.weights = {"w": word_weight, "b": bigram_weight, "c": char_weight}
        self.idf: dict[str, float] = {}

    def features(self, text: str) -> dict[str, float]:
        toks = tokens(text)
        feats: dict[str, float] = {}
        for t in toks:
            feats[f"w:{t}"] = feats.get(f"w:{t}", 0) + 1
            for g in char_ngrams(t):
                feats[f"c:{g}"] = feats.get(f"c:{g}", 0) + 1
        for a, b in zip(toks, toks[1:]):
            feats[f"b:{a}_{b}"] = feats.get(f"b:{a}_{b}", 0) + 1
        return feats

    def fit(self, texts: list[str]) -> "HashingEmbedder":
        """IDF per feature, so 'the printer' is about printers and not about common subwords like 'ing'."""
        df: dict[str, int] = {}
        for t in texts:
            for f in self.features(t):
                df[f] = df.get(f, 0) + 1
        n = len(texts)
        self.idf = {f: math.log((1 + n) / (1 + c)) + 1 for f, c in df.items()}
        return self

    def embed(self, text: str) -> Vector:
        vec = [0.0] * self.dim
        default_idf = math.log(1 + len(self.idf)) + 1 if self.idf else 1.0  # unseen features are rare ones
        for f, tf in self.features(text).items():
            i, sign = _bucket(f, self.dim)
            vec[i] += sign * self.weights[f[0]] * (1 + math.log(tf)) * self.idf.get(f, default_idf)
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec
