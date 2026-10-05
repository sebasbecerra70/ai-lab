"""Aspect extraction: map each sentence to product aspects by keyword, carry its sentiment, and rank pain points."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .sentiment import INTENSIFIERS, LEXICON, NEGATORS, score_text, sentences, tokens

ASPECTS = {
    "install": {"install", "installation", "setup", "wiring", "electrician", "furnace"},
    "app": {"app", "update", "logging", "reports"},
    "wifi": {"wifi", "connected", "connection", "router", "disconnects", "offline"},
    "battery": {"battery", "drains", "charge"},
    "accuracy": {"temperature", "accurate", "reading", "readings", "cold", "degrees"},
    "support": {"support", "service", "ticket", "reply", "replied"},
    "price": {"price", "expensive", "subscription", "value", "penny", "cost"},
    "schedule": {"schedule", "scheduling", "routine"},
}
STOP = set("the a an and or to of it is in on my i for was at with this that me have has be its every after even".split())


@dataclass
class Review:
    id: str
    rating: int
    text: str


@dataclass
class AspectStats:
    aspect: str
    mentions: int = 0
    negative: int = 0
    total_score: float = 0.0
    quotes: list[tuple[float, str, str]] = field(default_factory=list)  # (score, review id, sentence)
    secondary: int = 0  # mentioned in a sentence that is mainly about another aspect

    @property
    def avg(self) -> float:
        return self.total_score / self.mentions if self.mentions else 0.0

    @property
    def negative_share(self) -> float:
        return self.negative / self.mentions if self.mentions else 0.0

    @property
    def pain(self) -> float:
        """Pain index: how many reviews complain times how bad they sound. Volume and intensity both matter."""
        return sum(-s for s, _, _ in self.quotes if s < 0)


def load_reviews(path: Path) -> list[Review]:
    with open(path, newline="") as f:
        return [Review(r["id"], int(r["rating"]), r["text"]) for r in csv.DictReader(f)]


def aspects_in(sentence: str) -> list[str]:
    """Aspects in order of first mention. The first is usually the grammatical subject, i.e. what the complaint is about."""
    toks = tokens(sentence)
    first = {a: min(i for i, t in enumerate(toks) if t in kws) for a, kws in ASPECTS.items() if set(toks) & kws}
    return sorted(first, key=first.get)


def analyze(reviews: list[Review], neg_threshold: float = -0.1) -> dict[str, AspectStats]:
    stats = {a: AspectStats(a) for a in ASPECTS}
    for r in reviews:
        for s in sentences(r.text):
            score = score_text(s)
            found = aspects_in(s)
            if not found:
                continue
            # "The app crashes when I open the schedule" is an app problem: only the primary aspect gets the sentiment.
            st = stats[found[0]]
            st.mentions += 1
            st.total_score += score
            st.negative += score < neg_threshold
            st.quotes.append((score, r.id, s))
            for a in found[1:]:
                stats[a].secondary += 1
    return stats


def ranked_pains(stats: dict[str, AspectStats], top: int = 3) -> list[AspectStats]:
    return sorted((s for s in stats.values() if s.negative), key=lambda s: -s.pain)[:top]


def uncovered_terms(reviews: list[Review], top: int = 5) -> list[tuple[str, int]]:
    """Frequent words in negative sentences that no aspect covers: candidates for new aspects."""
    # Sentiment words say how people feel, not what about; skip them to surface topics.
    known = set().union(*ASPECTS.values(), LEXICON, INTENSIFIERS, NEGATORS, {"would"})
    counts: Counter = Counter()
    for r in reviews:
        for s in sentences(r.text):
            if score_text(s) < -0.1:
                counts.update(t for t in tokens(s) if t not in known and t not in STOP and len(t) > 3)
    return counts.most_common(top)


def rating_agreement(reviews: list[Review]) -> tuple[float, float]:
    """(Pearson r between review score and stars, polarity accuracy on clearly positive/negative reviews)."""
    xs = [score_text(r.text) for r in reviews]
    ys = [r.rating for r in reviews]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    r = cov / ((sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5)
    clear = [(x, y) for x, y in zip(xs, ys) if y != 3]
    acc = sum((x > 0) == (y > 3) for x, y in clear) / len(clear)
    return r, acc


def by_rating(reviews: list[Review]) -> dict[int, list[Review]]:
    out: dict[int, list[Review]] = defaultdict(list)
    for r in reviews:
        out[r.rating].append(r)
    return out
