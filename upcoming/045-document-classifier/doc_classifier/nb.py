"""Multinomial naive Bayes with Laplace smoothing, written from scratch."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from .features import featurize, words


@dataclass
class Prediction:
    label: str
    confidence: float          # posterior probability of the top label
    scores: dict[str, float]   # posterior per label
    evidence: int = 0          # in-vocabulary words seen: a 6-word scan fragment is weak evidence at any confidence

    @property
    def margin(self) -> float:
        top = sorted(self.scores.values(), reverse=True)
        return top[0] - (top[1] if len(top) > 1 else 0.0)


class NaiveBayes:
    def __init__(self, alpha: float = 0.5, char_n: int = 4, temperature: float = 1.0):
        self.alpha, self.char_n, self.temperature = alpha, char_n, temperature
        self.class_counts: Counter = Counter()
        self.feature_counts: dict[str, Counter] = defaultdict(Counter)
        self.totals: Counter = Counter()
        self.vocab: set[str] = set()

    def fit(self, texts: list[str], labels: list[str]) -> "NaiveBayes":
        for text, label in zip(texts, labels):
            f = featurize(text, self.char_n)
            self.class_counts[label] += 1
            self.feature_counts[label].update(f)
            self.totals[label] += sum(f.values())
            self.vocab.update(f)
        return self

    @property
    def labels(self) -> list[str]:
        return sorted(self.class_counts)

    def log_likelihoods(self, text: str) -> dict[str, float]:
        f = featurize(text, self.char_n)
        n_docs, v = sum(self.class_counts.values()), len(self.vocab)
        out = {}
        for c in self.labels:
            denom = self.totals[c] + self.alpha * v
            lp = math.log(self.class_counts[c] / n_docs)
            for tok, cnt in f.items():
                if tok in self.vocab:  # unseen features carry no evidence for any class
                    lp += cnt * math.log((self.feature_counts[c][tok] + self.alpha) / denom)
            out[c] = lp
        return out

    def predict(self, text: str) -> Prediction:
        pred = self.posterior(self.log_likelihoods(text))
        pred.evidence = sum(1 for w in words(text) if w in self.vocab and w != "0")
        return pred

    def posterior(self, ll: dict[str, float]) -> Prediction:
        # Naive Bayes is famously overconfident: correlated features (a word, its bigrams, its char n-grams)
        # each count as independent evidence, so posteriors pile up at 0.99+. temperature > 1 softens them;
        # routing also checks `evidence` because short fragments look just as "certain".
        scaled = {c: v / self.temperature for c, v in ll.items()}
        m = max(scaled.values())
        exp = {c: math.exp(v - m) for c, v in scaled.items()}
        z = sum(exp.values())
        post = {c: e / z for c, e in exp.items()}
        best = max(post, key=post.get)
        return Prediction(best, post[best], post)

    def top_features(self, label: str, k: int = 8, min_count: int = 5) -> list[tuple[str, float]]:
        """Features with the highest log-odds for `label` vs all other classes combined."""
        others = Counter()
        for c in self.labels:
            if c != label:
                others.update(self.feature_counts[c])
        ot = sum(others.values())
        mine, mt = self.feature_counts[label], self.totals[label]
        v = len(self.vocab)
        scored = [(f, math.log((mine[f] + self.alpha) / (mt + self.alpha * v)) - math.log((others[f] + self.alpha) / (ot + self.alpha * v)))
                  for f in mine if mine[f] >= min_count and not f.startswith("#")]
        return sorted(scored, key=lambda x: -x[1])[:k]
