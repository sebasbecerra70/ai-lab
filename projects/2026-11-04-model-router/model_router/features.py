"""Hand-built prompt features that correlate with task difficulty."""
from __future__ import annotations

import math
import re

REASONING_WORDS = {
    "analyze", "explain", "why", "design", "prove", "derive", "compare", "evaluate",
    "optimize", "debug", "refactor", "plan", "critique", "strategy", "trade-offs",
    "tradeoffs", "recommend", "justify", "implement", "reason", "architecture",
}
STEP_PHRASES = ("step by step", "step-by-step", "include tests", "root cause", "trade-off")
CODE_HINTS = ("python", "sql", "typescript", "function", "class", "stack trace", "code", "module")
CONSTRAINT_HINTS = ("constraint", "minimiz", "maximiz", "optimal", "under ", "no more than", "budget")

FEATURE_NAMES = [
    "log_words", "reasoning_words", "step_phrases", "code_hints",
    "constraint_hints", "numbers", "clauses", "question_only",
]


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z\-']*", text.lower())


def extract(text: str) -> list[float]:
    low = text.lower()
    words = tokenize(text)
    return [
        math.log1p(len(words)),
        float(sum(w.strip("'") in REASONING_WORDS for w in words)),
        float(sum(p in low for p in STEP_PHRASES)),
        float(sum(h in low for h in CODE_HINTS)),
        float(sum(h in low for h in CONSTRAINT_HINTS)),
        float(len(re.findall(r"\d+", text)) >= 3),
        float(low.count(",") + low.count(" and ")),
        float(text.strip().endswith("?") and len(words) < 10),
    ]
