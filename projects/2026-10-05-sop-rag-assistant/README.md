# SOP RAG Assistant

Ask plain-English questions about warehouse and logistics procedures, and get answers **grounded in your SOPs, with citations**. It refuses when the documents don't cover the question.

```text
$ python -m sop_rag "pallet arrived damaged"
Photograph the damage before unloading further, note it on the bill of lading ... [1]
  [1] receiving.md: ## Damaged inbound pallets
```

## Why it matters
Front-line staff lose time digging through SOP binders, and a generic chatbot will confidently make up procedures. Retrieval-augmented generation (RAG) limits the model to approved documents and shows where each answer came from.

## Architecture
```
question ──► TfidfRetriever ──► top-k SOP sections (score ≥ threshold)
                                   │ none? → "I don't know" (no LLM call)
                                   ▼
                       numbered context + strict system prompt
                                   ▼
                     LLMClient (MockLLM offline | AnthropicLLM)
                                   ▼
                          answer with [n] citations
```
- **Chunking:** one chunk per markdown section, so citations point to a specific procedure.
- **Retrieval:** dependency-free TF-IDF with cosine similarity. It sits behind a simple `search()` interface, so it can be swapped for embeddings plus a vector DB.
- **Guardrail:** a minimum relevance score blocks ungrounded answers before the model is called.
- **LLM boundary:** `LLMClient` is a one-method Protocol. Tests use a deterministic mock; set `ANTHROPIC_API_KEY` to use Claude.

## Run
```bash
pip install pytest
python -m pytest -q                      # 11 tests, offline
python -m sop_rag "how do I verify a trailer seal?"
ANTHROPIC_API_KEY=... python -m sop_rag "hazmat requirements"
```

## Next steps
- Swap TF-IDF for embeddings and compare recall on a labeled question set.
- Add an eval harness that checks citation faithfulness.
