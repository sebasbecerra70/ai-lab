# Semantic Search

Builds retrieval from first principles: **hashed n-gram embeddings**, a small **vector index** (exact scan plus IVF clustering), **BM25**, and **hybrid retrieval with reciprocal rank fusion**. It scores all three against a labelled query set so the choice of retriever rests on measured results.

```text
$ python -m semsearch
30 help-center articles, 20 labelled queries

retriever   recall@1  recall@3    MRR
bm25             80%       80%   0.80
dense            80%       95%   0.88
hybrid           85%       95%   0.90

Top hit per query (x = relevant doc not in top 3)
query                                     bm25      dense     hybrid
forgot my passwrd                         kb-001    kb-001    kb-001
pasword expired                           kb-002  x kb-001    kb-002
E4012                                     kb-002    kb-002    kb-002
vpn keeps failing to connect from home    kb-002    kb-012    kb-002
reimbursment for a client dinner          kb-002  x kb-005    kb-002
printer jammed P220                       kb-007    kb-007    kb-007
suspicious email asking for my login      kb-010    kb-016  x kb-010
maternity leave weeks                     kb-011    kb-011    kb-011
wifi disconnecting                        kb-012    kb-012    kb-012
computer is really slow                   kb-016    kb-016    kb-016
second screen not detected on dock        kb-017    kb-017    kb-017
unlocking my acount                       -       x kb-026    kb-026
restore a file I deleted                  kb-029    kb-029    kb-029
laptop backups                            kb-002  x kb-029    kb-009  x
new employee first week                   kb-009    kb-009    kb-009
encrypting usb sticks                     kb-022    kb-022    kb-022
lost my phone and can't approve MFA       kb-004    kb-004    kb-004
how much is the phone allowance           kb-021    kb-018    kb-021
what counts as SEV2                       kb-019    kb-027    kb-019
outlook calender not updating             kb-024    kb-024    kb-024

IVF index (6 clusters, probe 2): scores 10.1 of 30 docs per query on average; same top hit as the exact scan on 19/20 queries

$ python -m semsearch "my acount got locked"
[bm25]
   3.008  kb-026  Account locked out
[dense]
   0.153  kb-026  Account locked out
   0.085  kb-027  Work from abroad
   0.081  kb-009  Onboarding checklist for new hires
[hybrid]
   0.033  kb-026  Account locked out
   0.016  kb-027  Work from abroad
   0.016  kb-009  Onboarding checklist for new hires
```

## Why it matters
Retrieval quality limits every RAG system: if the right passage isn't in the top 3, the LLM either guesses or says it doesn't know. Users type the way they think, for example "pasword expired" or "unlocking my acount", while help articles are written by people who spell "password" correctly. On this help-center set **BM25 misses 4 of 20 queries entirely** (typos and inflections), while dense retrieval finds 19 of 20 in its top 3 but sometimes ranks a near-miss first. Hybrid fusion gives the best MRR (0.90) and top-1 hit rate (85%).

The per-query table shows the trade-offs. Exact codes such as `E4012` and `P220` are BM25's strength. Misspellings are dense retrieval's strength. "laptop backups" shows that fusion can also drag a correct dense answer down when BM25 is confidently wrong (it matches the word "laptop" in other articles), which makes it the first case to fix. With 20 labelled queries, each one moves a metric by 5 points, so a deflection team can see exactly which article or retriever to fix.

## Architecture
```
data/docs.jsonl ──► tokens(): lowercase, stopwords out, codes kept (e4012, sev2)
        │
        ├─► BM25 (k1=1.2, b=0.75) ───────────────────────► lexical ranking ──┐
        │                                                                    │
        └─► HashingEmbedder (1024-d, IDF-weighted)                           ├─► RRF: Σ 1/(60+rank)
              words + word bigrams + char 3-5grams                           │      = hybrid ranking
              blake2b hash → (bucket, ±sign), L2-normalized                  │
                       │                                                     │
                       ▼                                                     │
              VectorIndex: exact cosine scan ───────────► dense ranking ─────┘
                           IVF: spherical k-means (6 lists), probe 2 nearest
                                                     │
data/queries.json (20 labelled) ──► evaluate(): recall@1, recall@3, MRR per retriever
```
- **Hashing instead of a vocabulary.** There is no model file and nothing to download: any string maps to a fixed 1024-d vector. Character n-grams make it typo- and inflection-tolerant. The trade-off is that it has no real semantics: "maternity" only finds "parental leave" because the query also says "leave". A learned embedding model fixes that. The interfaces (`embed()` → vector, index → ids) are the same, so it is a drop-in swap.
- **Signed hashing plus IDF.** The sign hash makes collisions cancel out on average instead of piling up, and IDF stops common subwords such as `ing` from dominating the cosine.
- **RRF instead of score blending.** BM25 scores are unbounded and cosines are not, so blending them needs per-corpus tuning. Rank fusion has one constant (60) and holds up across corpora.
- **IVF over LSH.** Random-hyperplane LSH was the first version and matched the exact top hit on only 30% of queries. Short queries have low cosine with full articles, and LSH only works well for near-duplicates. Cluster-and-probe IVF matches 19/20 while scoring a third of the corpus.
- **Why not an LLM?** Retrieval has to be cheap, fast and deterministic, and an LLM belongs after this step as a reranker or answer writer. This project is the step that decides what the LLM gets to see.
- Standard library only. Building the index and running all 60 query-retriever evaluations takes under half a second.

## Run
```bash
pip install pytest
python -m pytest -q                          # 8 tests
python -m semsearch                          # eval table across retrievers
python -m semsearch "vpn certificate expired"  # ad-hoc query, all three retrievers
```
Swap in your own corpus with `data/docs.jsonl` (`id`, `title`, `text`) and label 20+ real queries from your search logs in `data/queries.json`.

## Next steps
- Add an LLM or cross-encoder reranker over the hybrid top 10, and measure the MRR gain against its latency and cost.
- Chunk long documents into passages so a single relevant paragraph is not diluted by the rest of a long article.
- Weight RRF per retriever and tune the weights on a held-out half of the labelled queries.
