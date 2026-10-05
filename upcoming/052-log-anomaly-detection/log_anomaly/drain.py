"""Drain-style online template mining: a fixed-depth parse tree routes each line to a small set of
candidate clusters; the most similar one absorbs it (differing tokens become <*>) or a new one is made."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MASKS = [
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<IP>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"(?<![A-Za-z0-9])-?\d+(?:\.\d+)?(?:%|G|M|K)?(?![A-Za-z0-9])"), "<NUM>"),
]
WILD = "<*>"


def mask(message: str) -> list[str]:
    for rx, token in MASKS:
        message = rx.sub(token, message)
    return message.split()


def _has_digit(tok: str) -> bool:
    return any(c.isdigit() for c in tok)


@dataclass
class Cluster:
    id: int
    template: list[str]
    size: int = 0

    @property
    def text(self) -> str:
        return " ".join(self.template)


@dataclass
class Drain:
    depth: int = 3            # how many leading tokens route through the tree
    sim_threshold: float = 0.5
    max_children: int = 50
    clusters: list[Cluster] = field(default_factory=list)
    _tree: dict = field(default_factory=dict)

    def _leaf(self, tokens: list[str]) -> list[Cluster]:
        node = self._tree.setdefault(len(tokens), {})
        for tok in tokens[: self.depth]:
            # tokens with digits (Ethernet1/12, FAN3) are likely parameters: route them through a wildcard branch
            key = WILD if _has_digit(tok) or tok.startswith("<") else tok
            if key not in node and len(node) >= self.max_children:
                key = WILD
            node = node.setdefault(key, {})
        return node.setdefault("__clusters__", [])

    @staticmethod
    def similarity(template: list[str], tokens: list[str]) -> tuple[float, int]:
        same = sum(a == b for a, b in zip(template, tokens) if a != WILD)
        wild = sum(a == WILD for a in template)
        return same / len(tokens), wild

    def add(self, message: str) -> Cluster:
        tokens = mask(message)
        if not tokens:
            tokens = ["<empty>"]
        leaf = self._leaf(tokens)
        best, best_key = None, (-1.0, 0)
        for c in leaf:
            sim, wild = self.similarity(c.template, tokens)
            key = (sim, -wild)  # prefer the more specific template on ties
            if key > best_key:
                best, best_key = c, key
        if best is None or best_key[0] < self.sim_threshold:
            best = Cluster(len(self.clusters), tokens[:])
            self.clusters.append(best)
            leaf.append(best)
        else:
            best.template = [a if a == b else WILD for a, b in zip(best.template, tokens)]
        best.size += 1
        return best
