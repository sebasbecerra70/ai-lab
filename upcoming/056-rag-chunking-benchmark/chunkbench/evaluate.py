"""Recall@k and MRR for one chunking strategy against a labeled question set."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .chunkers import Chunk, Doc, chunk_corpus
from .retrieval import BM25


@dataclass(frozen=True)
class Question:
    q: str
    doc: str
    answer: str


def load_questions(path: Path) -> list[Question]:
    return [Question(**x) for x in json.loads(path.read_text())]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def contains_answer(chunk: Chunk, q: Question) -> bool:
    """A hit needs the whole gold span inside one chunk's body. Half an answer split across two chunks is a
    miss, because that is exactly the failure that makes the model guess."""
    return chunk.doc == q.doc and norm(q.answer) in norm(chunk.text)


@dataclass
class Result:
    strategy: str
    size: int
    chunks: int
    avg_words: float
    recall: dict[int, float]
    mrr: float
    context_words: float   # average words sent to the model at k=3: the token bill
    ranks: list[int | None]  # 1-based rank of the first hit per question, None if not in the top 10
    unanswerable: int      # questions whose answer no chunk contains at all (a pure chunking failure)


def evaluate(docs: list[Doc], questions: list[Question], strategy: str, size: int = 100,
             ks: tuple[int, ...] = (1, 3, 5)) -> Result:
    chunks = chunk_corpus(docs, strategy, size)
    index = BM25([c.index_text for c in chunks])
    ranks: list[int | None] = []
    ctx = 0
    for q in questions:
        top = index.search(q.q, 10)
        ctx += sum(chunks[i].words for i in top[:3])
        ranks.append(next((r + 1 for r, i in enumerate(top) if contains_answer(chunks[i], q)), None))
    n = len(questions)
    recall = {k: sum(r is not None and r <= k for r in ranks) / n for k in ks}
    mrr = sum(1 / r for r in ranks if r) / n
    unanswerable = sum(not any(contains_answer(c, q) for c in chunks) for q in questions)
    return Result(strategy, size, len(chunks), sum(c.words for c in chunks) / len(chunks), recall, mrr,
                  ctx / n, ranks, unanswerable)
