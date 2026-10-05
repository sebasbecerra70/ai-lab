"""CLI: python -m semsearch ["your query"]"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import SearchEngine, evaluate, load_docs

MODES = ("bm25", "dense", "hybrid")


def main() -> None:
    data = Path(__file__).resolve().parent.parent / "data"
    engine = SearchEngine(load_docs(data / "docs.jsonl"))
    queries = json.loads((data / "queries.json").read_text())
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        for mode in MODES:
            print(f"[{mode}]")
            for doc_id, s in engine.search(query, mode, 3):
                print(f"  {s:6.3f}  {doc_id}  {engine.docs[doc_id]['title']}")
        return

    print(f"{len(engine.docs)} help-center articles, {len(queries)} labelled queries\n")
    print(f"{'retriever':<10}{'recall@1':>10}{'recall@3':>10}{'MRR':>7}")
    for mode in MODES:
        r1, r3 = evaluate(engine, queries, mode, 1), evaluate(engine, queries, mode, 3)
        print(f"{mode:<10}{r1['recall@1']:>10.0%}{r3['recall@3']:>10.0%}{r3['mrr']:>7.2f}")

    print("\nTop hit per query (x = relevant doc not in top 3)")
    print((f"{'query':<42}" + "".join(f"{m:<10}" for m in MODES)).rstrip())
    for q in queries:
        cells = []
        for mode in MODES:
            top = [d for d, _ in engine.search(q["q"], mode, 3)]
            mark = " " if set(top) & set(q["relevant"]) else "x"
            cells.append(f"{(top[0] if top else '-'):<8}{mark} ")
        print((f"{q['q'][:40]:<42}" + "".join(cells)).rstrip())

    idx = engine.index
    vecs = [engine.embedder.embed(q["q"]) for q in queries]
    scored = sum(len(idx.candidates(v)) for v in vecs) / len(vecs)
    agree = sum(idx.search_ivf(v, 1)[:1] == idx.search(v, 1) for v in vecs)
    print(f"\nIVF index ({idx.nlist} clusters, probe {idx.nprobe}): scores {scored:.1f} of {len(idx)} docs per query "
          f"on average; same top hit as the exact scan on {agree}/{len(vecs)} queries")

if __name__ == "__main__":
    main()
