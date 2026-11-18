"""CLI: python -m doc_classifier [file.txt ...]"""
import statistics
import sys
from pathlib import Path

from .docgen import generate
from . import NaiveBayes, cross_validate, evaluate, load_jsonl, needs_review

DATA = Path(__file__).resolve().parent.parent / "data"
THRESHOLD = 0.90
MIN_EVIDENCE = 8  # in-vocabulary words
SHORT = {"bill_of_lading": "BOL", "commercial_invoice": "INV", "packing_list": "PL", "customs_declaration": "CUS"}


def main() -> None:
    train, test = load_jsonl(DATA / "train.jsonl"), load_jsonl(DATA / "test.jsonl")
    model = NaiveBayes().fit([d["text"] for d in train], [d["label"] for d in train])

    if sys.argv[1:]:
        for path in sys.argv[1:]:
            p = model.predict(Path(path).read_text())
            route = "review" if needs_review(p, THRESHOLD, MIN_EVIDENCE) else "auto"
            print(f"{path}: {p.label} (conf {p.confidence:.2f}, {p.evidence} known words) -> {route}")
        return

    stress = generate(25, seed=123, noise=0.20)
    print(f"train {len(train)} docs (6% OCR noise), test {len(test)} docs (10%), stress {len(stress)} docs (20%)\n")
    print(f"{'features':<17}{'5-fold CV':>10}{'test':>8}{'stress':>8}")
    for name, kw in (("words + bigrams", {"char_n": 0}), ("+ char 4-grams", {"char_n": 4})):
        cv = cross_validate(train, k=5, **kw)
        m = NaiveBayes(**kw).fit([d["text"] for d in train], [d["label"] for d in train])
        print(f"{name:<17}{statistics.mean(cv):>10.1%}{evaluate(m, test).accuracy:>8.1%}{evaluate(m, stress).accuracy:>8.1%}")

    r = evaluate(model, test, THRESHOLD, MIN_EVIDENCE)
    print("\nconfusion (rows = true, cols = predicted)")
    print(f"{'':6}" + "".join(f"{SHORT[c]:>6}" for c in r.labels) + "  precision recall")
    for a in r.labels:
        print(f"{SHORT[a]:6}" + "".join(f"{r.confusion[a][p]:>6}" for p in r.labels) + f"  {r.precision[a]:>9.2f} {r.recall[a]:>6.2f}")
    print(f"\nrouting (confidence >= {THRESHOLD} and >= {MIN_EVIDENCE} known words): "
          f"{r.auto_rate:.0%} auto-filed at {r.auto_accuracy:.1%} accuracy, {len(r.review)} to review")
    for item in r.review[:5]:
        print(f"  review {item['id']:<10} guess {SHORT[item['pred']]:<4} conf {item['conf']:.2f}, "
              f"{item['evidence']} known words  (actually {SHORT[item['true']]})")

    print("\nmost telling features")
    for c in model.labels:
        print(f"  {SHORT[c]:<4} " + ", ".join(f for f, _ in model.top_features(c, 6)))


if __name__ == "__main__":
    main()
