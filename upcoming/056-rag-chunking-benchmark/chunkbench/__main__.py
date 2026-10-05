"""CLI: python -m chunkbench [chunk_size_words]"""
import sys
from pathlib import Path

from . import STRATEGIES, evaluate, load_docs, load_questions

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    docs, qs = load_docs(ROOT / "docs"), load_questions(ROOT / "data" / "questions.json")
    print(f"{len(docs)} docs, {sum(len(d.text.split()) for d in docs)} words, {len(qs)} labeled questions, "
          f"BM25, chunk size {size} words\n")
    print(f"{'strategy':<10}{'chunks':>7}{'avg wds':>8}{'R@1':>6}{'R@3':>6}{'R@5':>6}{'MRR':>6}{'ctx@3':>7}{'split':>6}")
    results = {s: evaluate(docs, qs, s, size) for s in STRATEGIES}
    for r in results.values():
        print(f"{r.strategy:<10}{r.chunks:>7}{r.avg_words:>8.0f}{r.recall[1]:>6.2f}{r.recall[3]:>6.2f}"
              f"{r.recall[5]:>6.2f}{r.mrr:>6.2f}{r.context_words:>7.0f}{r.unanswerable:>6}")
    print("(ctx@3 = avg words sent to the model at k=3; split = answers no single chunk contains)")

    print("\nRecall@3 by chunk size")
    sizes = (40, 70, 100, 150, 250)
    print(f"{'strategy':<10}" + "".join(f"{s:>7}" for s in sizes))
    for s in STRATEGIES:
        print(f"{s:<10}" + "".join(f"{evaluate(docs, qs, s, n).recall[3]:>7.2f}" for n in sizes))

    fx, hd = results["fixed"], results["heading"]
    print("\nWhere heading chunks win over fixed windows (rank of first correct chunk, - = not in top 10)")
    fmt = lambda r: str(r) if r else "-"
    for q, a, b in zip(qs, fx.ranks, hd.ranks):
        if (b or 99) < (a or 99) and (a is None or a > 3):
            print(f"  fixed {fmt(a):>2} heading {fmt(b):>2}  {q.q}")
    print("Where they lose")
    for q, a, b in zip(qs, fx.ranks, hd.ranks):
        if (a or 99) < (b or 99) and (b is None or b > 3):
            print(f"  fixed {fmt(a):>2} heading {fmt(b):>2}  {q.q}")


if __name__ == "__main__":
    main()
