"""Lexicon sentiment with negation, intensifiers and contrast ('but') handling."""
from __future__ import annotations

import re

LEXICON = {
    # positive
    "love": 2.0, "great": 1.5, "excellent": 2.0, "happy": 1.5, "easy": 1.0, "clear": 0.8, "clean": 0.8, "solid": 1.0,
    "accurate": 1.0, "helpful": 1.2, "friendly": 1.0, "fixed": 0.8, "worth": 1.2, "value": 0.8, "simple": 0.8,
    "saves": 1.0, "recommend": 1.5, "quickly": 0.6, "intuitive": 1.0, "works": 0.8, "reliable": 1.2, "lasts": 0.8, "stars": 0.5,
    # negative
    "nightmare": -2.5, "failed": -1.5, "slow": -1.0, "crashes": -2.0, "confusing": -1.2, "buggy": -1.5, "frustrating": -1.5,
    "drops": -1.2, "disconnects": -1.5, "reboot": -0.8, "dies": -1.8, "drains": -1.5, "blank": -1.0, "off": -0.6,
    "cold": -0.6, "never": -1.0, "useless": -2.0, "rude": -1.8, "waited": -1.0, "expensive": -1.2, "rip": -1.5,
    "resets": -1.0, "disappointed": -2.0, "problems": -1.0, "broken": -2.0, "terrible": -2.5,
}
NEGATORS = {"not", "no", "never", "without", "nothing", "dont", "doesnt", "didnt", "isnt", "wasnt", "cant", "wont"}
INTENSIFIERS = {"very": 1.5, "really": 1.4, "extremely": 1.8, "so": 1.3, "constant": 1.5, "always": 1.3, "too": 1.3}
TOKEN = re.compile(r"[a-z]+")
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower().replace("'", ""))


def score_text(text: str) -> float:
    """Sum of word scores, normalized to roughly [-1, 1]. Words after 'but' count double: they carry the verdict."""
    toks = tokens(text)
    total, weight = 0.0, 1.0
    for i, t in enumerate(toks):
        if t == "but":
            weight = 2.0
            continue
        s = LEXICON.get(t)
        if s is None:
            continue
        window = toks[max(0, i - 3):i]
        # "never" is itself negative; as a negator it only flips the *next* sentiment word ("never stays connected").
        if any(w in NEGATORS for w in window):
            s = -s * 0.8
        for w in window[-1:]:
            s *= INTENSIFIERS.get(w, 1.0)
        total += s * weight
    return max(-1.0, min(1.0, total / 3))


def sentences(text: str) -> list[str]:
    return [s for s in SENTENCE.split(text.strip()) if s]
