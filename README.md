# ai-lab

![tests](https://github.com/sebasbecerra70/ai-lab/actions/workflows/test.yml/badge.svg)

**Applied AI across operations, product, and business.** Small, working projects that use current AI and ML techniques on real business problems in data center operations, product management, business development and supply chain. Techniques include RAG, tool-calling agents, MCP servers, LLM evals, structured extraction, classic ML and optimization.

Each project is self-contained and has:
- a README covering the problem, why it matters, the architecture and how to run it;
- tests that run **offline**. LLM calls go through a small `LLMClient` interface with a deterministic mock, and setting `ANTHROPIC_API_KEY` switches to real model calls;
- standard-library-first code that's easy to read in one sitting.

## Projects
<!-- INDEX:START -->
| Date | Project | Technique | Domain | Stack |
|------|---------|-----------|--------|-------|
| 2026-10-05 | [SOP RAG Assistant](projects/2026-10-05-sop-rag-assistant): cited Q&A over warehouse SOPs | RAG, grounding guardrails | Supply Chain | Python |
| 2026-10-05 | [Tool-Calling Ops Agent](projects/2026-10-05-tool-calling-agent): Agent loop that answers ops questions with calculator, lookup and unit tools | tool-calling agent | AI Engineering | Python |
| 2026-10-06 | [Data Center Capacity Planner](projects/2026-10-06-datacenter-capacity-planner): Power, cooling and space headroom per hall with a run-out forecast | scenario simulation | Data Center Ops | Python |
| 2026-10-07 | [Feature Request Clustering](projects/2026-10-07-feature-request-clustering): TF-IDF + k-means groups feature requests; an LLM names each theme | TF-IDF, k-means, LLM labeling | Product | Python |
| 2026-10-08 | [Explainable Lead Scoring](projects/2026-10-08-lead-scoring-model): From-scratch logistic regression that scores B2B leads and says why | logistic regression | Business Development | Python |
| 2026-10-09 | [Invoice Extraction with Guardrails](projects/2026-10-09-invoice-extraction): LLM pulls invoice fields to a JSON schema; validation and regex catch errors | LLM structured extraction | Supply Chain | Python |
| 2026-10-10 | [LLM Eval Harness](projects/2026-10-10-llm-eval-harness): Code-defined test cases, four grader types and a CI gate for LLM apps | LLM evaluation, LLM-as-judge | AI Engineering | Python |
| 2026-10-11 | [Alert Triage Assistant](projects/2026-10-11-alert-triage-assistant): Dedupes and correlates monitoring alerts, scores severity, drafts on-call notes | topology correlation + LLM summary | Data Center Ops | Python |
| 2026-10-12 | [RICE Prioritizer](projects/2026-10-12-rice-prioritizer): RICE scores, Monte Carlo rank confidence and a capacity-aware roadmap | scoring model, Monte Carlo sensitivity | Product | TypeScript |
| 2026-10-13 | [RFP Answer Drafter](projects/2026-10-13-rfp-answer-rag): RAG over past proposals drafts cited RFP answers or routes them to SMEs | RAG (BM25) with confidence threshold | Business Development | Python |
| 2026-10-14 | [Demand Forecasting Baselines](projects/2026-10-14-demand-forecasting): Naive, moving average, Holt-Winters and Croston, compared by backtest WAPE | time-series forecasting, backtesting | Supply Chain | Python |
| 2026-10-15 | [Inventory MCP Server](projects/2026-10-15-mcp-server-inventory): Dependency-free MCP server exposing inventory tools and resources over stdio | Model Context Protocol (JSON-RPC 2.0), tool schemas | AI Engineering | TypeScript |
| 2026-10-16 | [Rack Placement Optimizer](projects/2026-10-16-rack-placement-optimizer): Bin-pack servers into racks under power, U-space and anti-affinity rules | bin-packing heuristics (FFD, BFD, consolidation pass) | Data Center Ops | Python |
| 2026-10-17 | [A/B Test Analyzer](projects/2026-10-17-ab-test-analyzer): Z-tests, confidence intervals, power planning and SRM checks for experiments | frequentist hypothesis testing, power analysis, chi-square SRM | Product | Python |
| 2026-10-18 | [CRM Pipeline Forecast](projects/2026-10-18-crm-pipeline-forecast): Stage-weighted and Monte Carlo quarterly forecast with deal-aging decay | empirical stage conversion, Monte Carlo simulation | Business Development | Python |
| 2026-10-19 | [Delivery Route Optimizer](projects/2026-10-19-route-optimization): Capacitated vehicle routing with Clarke-Wright savings and 2-opt | Clarke-Wright savings heuristic, 2-opt local search | Supply Chain | Python |
| 2026-10-20 | [LLM-as-Judge with Bias Checks](projects/2026-10-20-llm-as-judge): Pairwise and rubric LLM judging with position-swap and human agreement stats | LLM-as-judge, position-bias swap, Cohen's kappa | AI Engineering | Python |
| 2026-10-21 | [Incident Postmortem Generator](projects/2026-10-21-incident-postmortem-generator): Merge logs and incident chat into a timeline, then draft a blameless postmortem | log parsing, event classification, grounded LLM drafting with checks | Data Center Ops | Python |
| 2026-10-22 | [PRD Drafter](projects/2026-10-22-prd-drafter): Structured PM interview, LLM-filled PRD template and a completeness checker | structured elicitation, templated LLM generation, rule-based doc linting | Product | TypeScript |
| 2026-10-23 | [Account Research Agent](projects/2026-10-23-account-research-agent): Tool-using agent reads company profiles and writes a cited account brief | multi-step tool-calling agent, BM25 search, citation grounding check | Business Development | Python |
| 2026-10-24 | [Inventory Reorder Agent](projects/2026-10-24-inventory-reorder-agent): Reorder points and EOQ drive PO proposals routed by approval thresholds | safety stock / ROP / EOQ, policy-gated agent with LLM memos | Supply Chain | Python |
| 2026-10-25 | [Prompt Injection Guardrails](projects/2026-10-25-prompt-injection-guardrails): Input/output guard pipeline: injection scoring, PII redaction, tool allow-list | heuristic injection detection, PII redaction, policy-checked tool calls | AI Engineering | Python |
| 2026-10-26 | [Disk Failure Prediction](projects/2026-10-26-disk-failure-prediction): Logistic regression on SMART-like telemetry with a cost-optimal alert threshold | logistic regression, precision/recall at threshold, cost curve | Data Center Ops | Python |
| 2026-10-27 | [Review Sentiment Insights](projects/2026-10-27-review-sentiment-insights): Lexicon sentiment and aspect extraction rank pain points; an LLM writes the brief | lexicon sentiment with negation, aspect extraction, grounded LLM summary | Product | Python |
| 2026-10-28 | [Pricing Simulator](projects/2026-10-28-pricing-simulator): Price elasticity what-ifs, pocket-price waterfall and discount break-even | log-log elasticity regression, constant-elasticity demand, price waterfall | Business Development | TypeScript |
| 2026-10-29 | [Shipment Delay Risk](projects/2026-10-29-shipment-delay-risk): Boosted decision stumps that score delay risk per lane, carrier and load | AdaBoost decision stump ensemble | Supply Chain | Python |
| 2026-10-30 | [Semantic Search](projects/2026-10-30-semantic-search): Hashed n-gram embeddings, an LSH vector index and BM25 hybrid retrieval | hashed embeddings, BM25, reciprocal rank fusion | AI Engineering | Python |
<!-- INDEX:END -->

## How projects are published
Projects are built and tested in batches, then queued in [`upcoming/`](upcoming). A scheduled GitHub Action ([`publish.yml`](.github/workflows/publish.yml)) releases one per day. It re-runs the project's tests, moves it into `projects/` and adds it to the index. Projects are built with AI assistance (Claude).

Conventions for adding a project are in [CONVENTIONS.md](CONVENTIONS.md).
