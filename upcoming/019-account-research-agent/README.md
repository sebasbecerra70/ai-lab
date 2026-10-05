# Account Research Agent

A tool-using agent that researches a target account from local company profiles and writes a **cited account brief**: snapshot, ICP fit, why now, pains mapped to our product, who to talk to, and an opener. Every bullet links back to the document section it came from, and a grounding check rejects citations the agent never actually read.

```text
$ python -m account_agent "Harbor Retail"
agent: MockLLM, target: Harbor Retail
  step 1: list_companies() -> [{"doc": "evergreen_foods", "name": "Evergreen Foods"}, {"doc": "harbo...
  step 2: read_section(doc='harbor_retail', section='Overview') -> {"ref": "harbor_retail#Overview", ...
  step 3: score_fit(doc='harbor_retail') -> {"score": 3, "max": 4, "reasons": [...
  step 4: read_section(doc='harbor_retail', section='Recent news') -> ...
  step 5: read_section(doc='harbor_retail', section='Leadership') -> ...
  step 6: search(query='stockouts lost sales overstock markdowns spreadsheets manual transfers', doc='harbor_retail') -> ...
  step 7: read_section(doc='our_product', section='Capabilities') -> ...

# Account brief: Harbor Retail
## Fit: 3/4
- 50+ locations: met (212) [harbor_retail#Overview]
- 10k+ SKUs: not met (no evidence)
- inventory above $50M: met ($610M) [harbor_retail#Financials]
- ERP/WMS change or new DC in flight: met (replace a legacy merchandising system) [harbor_retail#Recent news]
## Why now
- On the last earnings call the CFO said stockouts on top sellers cost an estimated $45M in lost sales while seasonal overstock drove markdowns. [harbor_retail#Recent news]
- Selected SAP S/4HANA to replace a legacy merchandising system; migration is in phase one. [harbor_retail#Recent news]
## Pains and plays
- stockout -> replenishment [harbor_retail#Recent news] [our_product#Capabilities]
- overstock -> forecasting [harbor_retail#Recent news] [our_product#Capabilities]
- transfers -> rebalancing [harbor_retail#Operations] [our_product#Capabilities]
## Who to talk to
- Priya Raman, SVP Supply Chain (joined from a national grocery chain eight months ago) [harbor_retail#Leadership]
- Tom Becker, VP Merchandise Planning [harbor_retail#Leadership]
## Suggested opener
Saw that Harbor Retail announced a new 600,000 sq ft distribution center in Columbus. Teams opening a DC usually re-set replenishment rules ...

grounding: 6 sources cited, unseen=[], uncited bullets=0

ICP fit across all profiles:
  Evergreen Foods  1/4  ERP/WMS change or new DC in flight
  Harbor Retail    3/4  50+ locations, inventory above $50M, ERP/WMS change or new DC in flight
  Juniper Pharma   2/4  10k+ SKUs, inventory above $50M
  Pinnacle Steel   1/4  inventory above $50M
```

## Why it matters
Account executives and BDRs typically spend 30–60 minutes per account before a first call, reading 10-Ks, news and LinkedIn, and much of that work never reaches the CRM. At 15 target accounts a week, that's one or two days of a seller's week. An agent that produces a consistent, cited brief in seconds gives that time back to selling. Because every line cites its source, the rep can check the important claims in a minute instead of trusting a summary.

The structure also reflects how good BD people think. **Why now** (a new DC, an ERP migration, a CFO quantifying $45M of lost sales) matters more than the company description. **Fit** is scored against the ICP explicitly, so the territory is ranked (Harbor 3/4, Pinnacle 1/4) before anyone spends time on it. And "10k+ SKUs: no evidence" is listed as an unknown to ask about in discovery, not guessed.

## Architecture
```
               ┌──────────── ResearchAgent.run(account) ─────────────┐
TARGET +       │ loop ≤ max_steps:                                    │
HISTORY ──────►│   LLM → {"tool", "args"} | {"final": brief}          │
(JSON)         │   run tool → observation (errors returned, not raised)│
               │   collect refs seen                                  │
               └───────────────┬──────────────────────────────────────┘
                               │ tools over DocStore (data/companies/*.md, data/our_product.md)
     list_companies · read_section(doc, section) · search (BM25) · extract_signals (regex) · score_fit (ICP rules)
                               │
                               ▼
              check_citations(brief, seen_refs): unseen refs · uncited bullets
LLMClient: MockLLM (deterministic research plan) | AnthropicLLM (ANTHROPIC_API_KEY)
```
- **Tools return citations.** Every observation carries a `doc#Section` ref, and the agent tracks which refs it has seen. The grounding check is then a set difference, which is cheap and catches the worst hallucination: citing something that was never read.
- **Deterministic where possible.** ICP fit and signal extraction are rules over parsed numbers, not LLM judgement, so the same account always gets the same score and a manager can audit the scoring.
- **Errors are observations.** A bad section name returns the list of valid sections, so the model can correct itself. Unknown tools and a step budget stop runaway loops.
- **Unknowns are explicit.** A missing criterion is shown as "(no evidence)" and exempt from the citation rule, because admitting a gap isn't a factual claim.
- **Trade-off:** a local document store instead of web search keeps this offline, reproducible and testable. In production the same tool interface would wrap a news API, SEC filings and the CRM, and the grounding check would matter even more.

## Run
```bash
python -m pytest -q                                  # 10 tests, offline
python -m account_agent "Harbor Retail"
python -m account_agent "Juniper Pharma"
ANTHROPIC_API_KEY=... python -m account_agent "Harbor Retail"   # Claude chooses the tool calls
```

## Next steps
- Add tools for CRM history (past opportunities, open tickets) and a news API with dated sources.
- Use Claude's native tool-use API instead of JSON-in-text once the tool set grows.
- Score briefs with an LLM judge for specificity and track which briefs led to meetings booked.
- Batch mode: rank a whole territory by fit and write briefs only for the top N.
