"""Heuristic prompt-injection scoring. Cheap, explainable, and meant to run before every model call."""
from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass

# (name, weight, pattern). Weights are additive; tuned on data/attacks.jsonl.
PATTERNS = [
    ("override", 0.6, r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|your)\b.{0,20}\b(instructions?|rules|prompts?|guidelines)"),
    ("new_persona", 0.45, r"\byou are (now|no longer)\b|\bact as\b.{0,30}\b(unrestricted|jailbroken|dan|developer mode)\b|\bdeveloper mode\b"),
    ("prompt_leak", 0.5, r"\b(reveal|print|show|repeat|output)\b.{0,40}\b(system|hidden|initial|original)\s+(prompt|instructions|message)"),
    ("fake_delimiter", 0.45, r"</?(system|assistant|instructions?)>|\[/?(system|INST)\]|^#{2,}\s*(system|new instructions)", ),
    ("tool_coercion", 0.35, r"\b(call|use|invoke|run)\b.{0,20}\b(tool|function|refund|send_email|transfer)\b.{0,60}\b(now|immediately|without (asking|confirmation|approval))"),
    ("exfil_url", 0.4, r"!\[[^\]]*\]\(https?://[^)]*\?[^)]*=|\b(send|post|forward|upload)\b.{0,40}\bhttps?://"),
    ("addressed_to_ai", 0.3, r"\b(ai|assistant|chatbot|language model|llm)\s*(:|,)?\s*(please\s+)?(must|should|ignore|do not|don't)\b"),
    ("secrecy", 0.25, r"\b(do not|don't) (tell|inform|mention|reveal)\b.{0,30}\b(user|customer|anyone|human)"),
]
COMPILED = [(n, w, re.compile(p, re.I | re.M)) for n, w, p in PATTERNS]
ZERO_WIDTH = re.compile(r"[​-‏⁠-⁤﻿]")
B64 = re.compile(r"\b[A-Za-z0-9+/]{24,}={0,2}")


@dataclass(frozen=True)
class InjectionResult:
    score: float
    hits: tuple[str, ...]
    decision: str  # allow | flag | block


def normalize(text: str) -> tuple[str, list[str]]:
    """Undo common obfuscation: zero-width characters, full-width letters, base64-wrapped payloads."""
    notes = []
    if ZERO_WIDTH.search(text):
        notes.append("zero_width_chars")
        text = ZERO_WIDTH.sub("", text)
    folded = unicodedata.normalize("NFKC", text)
    if folded != text:
        notes.append("unicode_confusables")
        text = folded
    for blob in B64.findall(text):
        try:
            decoded = base64.b64decode(blob, validate=True).decode("utf-8")
        except Exception:
            continue
        if decoded.isprintable():
            notes.append("base64_payload")
            text += "\n" + decoded
    return text, notes


def score_injection(text: str, source: str = "user", block_at: float = 0.6, flag_at: float = 0.3) -> InjectionResult:
    """source='document' is for retrieved content: it should contain no instructions at all, so thresholds are lower."""
    clean, notes = normalize(text)
    hits = [n for n, _, rx in COMPILED if rx.search(clean)]
    score = sum(w for n, w, _ in COMPILED if n in hits) + 0.2 * len(notes)
    if source == "document":
        block_at, flag_at = block_at - 0.2, flag_at - 0.15
    decision = "block" if score >= block_at else "flag" if score >= flag_at else "allow"
    return InjectionResult(round(min(score, 1.5), 2), tuple(hits + notes), decision)
