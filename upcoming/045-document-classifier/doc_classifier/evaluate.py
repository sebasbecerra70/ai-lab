"""Accuracy, per-class precision/recall, confusion matrix, k-fold CV and a confidence-based review queue."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from .nb import NaiveBayes


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@dataclass
class Report:
    labels: list[str]
    confusion: dict[str, dict[str, int]]
    accuracy: float
    precision: dict[str, float]
    recall: dict[str, float]
    auto_rate: float = 1.0       # share of docs above the confidence threshold
    auto_accuracy: float = 1.0   # accuracy on that auto-routed share
    review: list[dict] = field(default_factory=list)


def needs_review(pred, threshold: float, min_evidence: int) -> bool:
    return pred.confidence < threshold or pred.evidence < min_evidence


def evaluate(model: NaiveBayes, docs: list[dict], threshold: float = 0.0, min_evidence: int = 0) -> Report:
    labels = model.labels
    conf = {a: {p: 0 for p in labels} for a in labels}
    auto, auto_ok, review = 0, 0, []
    for d in docs:
        pred = model.predict(d["text"])
        conf[d["label"]][pred.label] += 1
        if not needs_review(pred, threshold, min_evidence):
            auto += 1
            auto_ok += pred.label == d["label"]
        else:
            review.append({"id": d["id"], "pred": pred.label, "conf": pred.confidence, "evidence": pred.evidence,
                           "true": d["label"]})
    n = len(docs)
    acc = sum(conf[c][c] for c in labels) / n
    precision = {c: conf[c][c] / max(sum(conf[a][c] for a in labels), 1) for c in labels}
    recall = {c: conf[c][c] / max(sum(conf[c].values()), 1) for c in labels}
    return Report(labels, conf, acc, precision, recall, auto / n, auto_ok / max(auto, 1), review)


def cross_validate(docs: list[dict], k: int = 5, seed: int = 0, **model_kw) -> list[float]:
    docs = docs[:]
    random.Random(seed).shuffle(docs)
    folds = [docs[i::k] for i in range(k)]
    scores = []
    for i in range(k):
        train = [d for j, f in enumerate(folds) if j != i for d in f]
        model = NaiveBayes(**model_kw).fit([d["text"] for d in train], [d["label"] for d in train])
        scores.append(evaluate(model, folds[i]).accuracy)
    return scores

