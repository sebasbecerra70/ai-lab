"""Retrieval-augmented Q&A over warehouse / logistics SOPs with citations."""
from __future__ import annotations

from dataclasses import dataclass

from .llm import LLMClient
from .retriever import Chunk, TfidfRetriever

SYSTEM = (
    "You answer questions for warehouse and logistics staff using ONLY the numbered SOP "
    "passages provided. Cite passages like [1]. If the passages don't contain the answer, "
    "say you don't know based on the provided SOPs."
)


@dataclass
class Answer:
    text: str
    sources: list[Chunk]


class SOPAssistant:
    def __init__(self, retriever: TfidfRetriever, llm: LLMClient, k: int = 3, min_score: float = 0.05):
        self.retriever, self.llm, self.k, self.min_score = retriever, llm, k, min_score

    def ask(self, question: str) -> Answer:
        hits = [c for c, s in self.retriever.search(question, self.k) if s >= self.min_score]
        if not hits:
            # Refuse rather than let the model guess without grounding.
            return Answer("I don't know based on the provided SOPs.", [])
        context = "\n".join(f"[{i}] source: {c.source}\n{c.text}" for i, c in enumerate(hits, 1))
        prompt = f"SOP passages:\n{context}\n\nQuestion: {question}"
        return Answer(self.llm.complete(SYSTEM, prompt), hits)
