# RAG Chunking Benchmark

Measures how the chunking strategy changes retrieval quality on a labeled question set. It compares fixed word windows, sentence packing and heading-aware sections using the same BM25 retriever, and reports recall@k, MRR and the context bill.

```text
$ python -m chunkbench
8 docs, 2090 words, 47 labeled questions, BM25, chunk size 100 words

strategy   chunks avg wds   R@1   R@3   R@5   MRR  ctx@3 split
fixed          26      88  0.83  0.94  0.98  0.89    274     0
sentence       24      80  0.83  1.00  1.00  0.90    250     0
heading        53      36  0.98  0.98  0.98  0.98    113     0
(ctx@3 = avg words sent to the model at k=3; split = answers no single chunk contains)

Recall@3 by chunk size
strategy       40     70    100    150    250
fixed        0.91   0.96   0.94   1.00   0.98
sentence     0.96   0.96   1.00   0.98   1.00
heading      0.98   0.98   0.98   0.98   0.98

Where heading chunks win over fixed windows (rank of first correct chunk, - = not in top 10)
  fixed  6 heading  1  What's the hotel limit per night in London?
  fixed  5 heading  1  What is the retention period for audit logs?
  fixed  4 heading  1  What is the home office setup allowance for remote employees?
Where they lose
  fixed  3 heading  6  How long do I have to acknowledge a page when I'm the primary on call?
```

## Why it matters
Most RAG failures that get blamed on "the model hallucinated" are retrieval failures: the right paragraph never reached the prompt. Chunking is the cheapest lever and the one most teams leave at a tutorial default of fixed 512-token windows. On this policy handbook, heading-aware chunks put the right passage first for 98% of questions, against 83% for fixed windows. They do it while sending **less than half the context** (113 vs 274 words at k=3), which is a direct cut in input tokens per query. At equal chunk size (`python -m chunkbench 40`) the gap is wider: 0.94 vs 0.68 recall@1.

The failures follow a pattern. Policy documents put the subject in the heading ("### Hotels") and write the body as "The nightly cap is 250 dollars". A fixed window has dropped the heading, so for "What's the hotel limit per night in London?" it ranks remote-work and on-call windows first and the right passage sixth. One window boundary even falls between "250" and "dollars in tier one cities". A 47-question labeled set turns that from an argument into a number you can track in CI whenever the corpus or the chunker changes.

## Architecture
```
docs/*.md ──► chunkers ──────────────────────────────────────────────┐
              fixed(size, 20% overlap)   words only, headings dropped│
              sentence(size)             packs whole sentences       │
              heading(size)              one section per chunk,      │
                                         split at sentences if long, │
                                         heading path in index text  │
                                                                     ▼
data/questions.json ──► BM25 (from scratch) over chunk.index_text ──► top 10
 (question, doc, gold answer span)                                    │
                                                                      ▼
                     hit = whole gold span inside one chunk body of the right doc
                                                                      │
                                                                      ▼
                    recall@1/3/5, MRR, avg context words at k=3, unanswerable count
```
- **The index text is separate from the body.** The heading path ("Expense Policy > Travel > Hotels") is indexed but not counted as answer text, so heading chunks can't win by matching the gold span against their own titles.
- **A strict hit definition.** The full gold span has to be inside a single chunk. An answer cut across two windows counts as a miss, because a model shown half of "rotated automatically within 1 hour" will guess the rest. The `split` column counts questions that no chunk could answer at all.
- **BM25 and not embeddings**, on purpose. It is deterministic, standard library and fast, so the benchmark isolates the chunking variable. The harness takes any retriever with `search(query, k)`, so a dense or hybrid retriever slots in for a second comparison.
- **The context bill is reported next to recall.** Bigger chunks raise recall@k almost for free (fixed reaches 1.00 at 150 words), but you pay for it in every prompt. ctx@3 makes that trade-off visible.
- **No LLM in the loop.** Retrieval quality is measurable without generation, which keeps the benchmark free, reproducible and runnable in CI. An LLM-as-judge step for answer quality belongs downstream of this one.
- **Where heading chunks lose.** Short sections like "### Primary" rely entirely on their heading. A question about pages can then match a longer escalation paragraph in another document. The report prints those losses as well as the wins.

## Run
```bash
pip install pytest
python -m pytest -q          # 11 tests
python -m chunkbench         # 100-word chunks
python -m chunkbench 40      # equal small chunks: the gap widens
```
Add questions to `data/questions.json` as `{"q", "doc", "answer"}`. A test checks that every gold span exists verbatim in its document.

## Next steps
- Add a hashed-embedding retriever and a BM25 + embedding hybrid to see whether chunking still matters once retrieval is semantic.
- Try parent-child retrieval: match on small heading chunks, then send the parent section.
- Generate candidate questions per section with an LLM, then have a human label them, to grow the set past 200 questions.
