# ai-lab

![tests](https://github.com/sebasbecerra70/ai-lab/actions/workflows/test.yml/badge.svg)

Small, working projects exploring **current AI techniques applied to supply chain and logistics**: RAG, agents and tool calling, MCP servers, evals, structured extraction, embeddings, and forecasting copilots.

Each project is self-contained and has:
- a README covering the problem, why it matters, the architecture and how to run it;
- tests that run **offline**. LLM calls go through a small `LLMClient` interface with a deterministic mock, and setting `ANTHROPIC_API_KEY` switches to real model calls;
- standard-library-first code that's easy to read in one sitting.

## Projects
<!-- INDEX:START -->
| Date | Project | AI technique | Stack |
|------|---------|--------------|-------|
| 2026-10-05 | [SOP RAG Assistant](projects/2026-10-05-sop-rag-assistant): cited Q&A over warehouse SOPs | RAG, grounding guardrails | Python |
<!-- INDEX:END -->

Conventions for adding a project are in [CONVENTIONS.md](CONVENTIONS.md).
