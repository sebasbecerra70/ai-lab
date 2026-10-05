# KPI Narrator

Turns a monthly KPI table into an executive summary. Deterministic code does the variance analysis: RAG against tolerance, favorable vs unfavorable by metric direction, and a price-volume-mix revenue bridge. An LLM writes the narrative, and a **number-faithfulness check** rejects any draft that misquotes a number, gets a direction wrong or leaves out a red KPI, then sends the problems back for a repair.

```text
$ python -m kpi_narrator
  KPI                       actual      plan   vs plan      %  vs prior  status
! Revenue                   $4.23M    $4.45M    -$216k  -4.9%     +$52k  red (unfavorable)
  Orders shipped            61,240    63,000    -1,760  -2.8%    +1,370  green (unfavorable)
! On-time delivery           93.1%     96.0%   -2.9 pp  -3.0%   -2.3 pp  red (unfavorable)
! Order cycle time          31.5 h    28.0 h    +3.5 h +12.5%    +2.3 h  red (unfavorable)
~ Cost per order             $7.42     $7.10    +$0.32  +4.5%    +$0.24  amber (unfavorable)
  Warehouse utilization      86.5%     85.0%   +1.5 pp  +1.8%   +2.4 pp  green
  Inventory turns              8.4       8.0      +0.4  +5.0%      +0.3  green
! Backorder rate              2.9%      2.0%   +0.9 pp +45.0%   +0.7 pp  red (unfavorable)
  Safety incidents               1         2        -1 -50.0%        -2  green
! Employee turnover           4.8%      3.5%   +1.3 pp +37.1%   +0.9 pp  red (unfavorable)
~ Customer NPS                  41        45        -4  -8.9%        -3  amber (unfavorable)

Revenue bridge: plan $4.45M | volume -$124k | mix -$114k | price +$23k | actual $4.23M
   Retail     volume    -$48k  mix    -$69k  price    +$29k
   Wholesale  volume    -$28k  mix   +$121k  price    -$53k
   E-commerce volume    -$47k  mix   -$166k  price    +$47k

draft 1: 4 issue(s)
   - number not in facts: $0.25M
   - wrong verdict for Backorder rate: unfavorable
   - wrong verdict for Employee turnover: unfavorable
   - wrong verdict for Order cycle time: unfavorable

draft 2: passes the number and direction check

Executive summary (llm, 2 attempt(s))
------------------------------------------------------------
Headline: 4 of 11 KPIs on plan, 5 red. Revenue was $4.23M, $216k below plan (-4.9%).
Backorder rate missed plan at 2.9% vs 2.0% (+0.9 pp); owner Inventory.
Employee turnover missed plan at 4.8% vs 3.5% (+1.3 pp); owner HR.
On-time delivery missed plan at 93.1% vs 96.0% (-2.9 pp); owner Fulfillment.
Order cycle time missed plan at 31.5 h vs 28.0 h (+3.5 h); owner Fulfillment.
Revenue missed plan at $4.23M vs $4.45M (-$216k); owner VP Sales.
Bright spots: Warehouse utilization 86.5% vs 85.0%, Inventory turns 8.4 vs 8.0, Safety incidents 1 vs 2.
Revenue bridge: volume -$124k, mix -$114k, price +$23k; E-commerce is the biggest drag at -$166k.
Asks: Inventory to bring a recovery plan for Backorder rate; HR to bring a recovery plan for Employee turnover; Fulfillment to bring a recovery plan for On-time delivery.
```

## Why it matters
Every month an operations analyst spends a day turning the same KPI table into the same kind of summary, and the team reads it in five minutes. An LLM can write that summary in seconds. The risk is that it writes "revenue was $0.25M below plan" when the gap was $216k, or says "order cycle time beat plan" because 31.5 is a bigger number than 28.0. One wrong number in an exec summary costs more credibility than the analyst-day saves, so the value here is in the check, not the generation.

In the sample month, the first draft has four such errors. The check catches all of them and sends them back, and the repair draft passes. If it hadn't, the reader would get a plain template that is correct by construction. The bridge adds the "why" that a variance table can't show: revenue is $216k short, mostly from **volume (-$124k) and mix (-$114k)**, because high-price e-commerce units came in 13% under plan. Price actually helped (+$23k). "Sell more e-commerce" and "raise prices" are very different asks of the sales team.

## Architecture
```
data/kpis.csv ───────────► variance(): vs plan / prior, favorable given direction,
                           RAG = green within tolerance, amber to 2x, red beyond (zero tolerance: any miss)
data/revenue_drivers.csv ─► bridge(): plan ─ volume ─ mix ─ price ─► actual (reconciles exactly)
                                   │
                                   ▼
                     build_facts(): every number pre-formatted by fmt(), sorted by severity
                                   │
                                   ▼
             ┌──► LLMClient.complete(SYSTEM, FACTS [+ draft + problems])
             │          MockLLM (offline)  |  AnthropicLLM (stdlib HTTP, if ANTHROPIC_API_KEY)
             │                     │
             │                     ▼
             │    check(): numbers   each one a correct rounding of some fact ($4.2M ok, $4.3M not)
             │             direction above/below = raw value; beat/missed = favorable given direction
             │             coverage  every red KPI is mentioned
             └── issues? repair once ── still failing? ──► template()
```
- **Code computes and the model writes.** The LLM never does arithmetic. It gets pre-formatted facts and is told to copy them. The bridge, the RAG status and the ordering are deterministic and tested, including a test that the three bridge effects add up to actual minus plan exactly.
- **The faithfulness check is precision-aware.** "$4.23M" means 4,230,000 ± 5,000, and "$4.2M" means ± 50,000. A number passes if it is a correct rounding of some fact, so the model can simplify but can't invent. Units (M, k, %, pp) are parsed, not ignored.
- **Direction is the subtle error.** For lower-is-better metrics (cycle time, cost per order, turnover), "above plan" and "missed plan" are both true at once. The check separates raw-direction words from verdict words, because that is exactly where both models and people slip.
- **Repair, then fall back.** The problems go back to the model in a second prompt. That is cheaper and more reliable than retrying blindly. After the attempt limit, the template wins: a dull summary is better than a wrong one.
- **Classic analytics where they fit.** Price-volume-mix is a forty-year-old FP&A tool, and it answers "why" better than any model would guess. The LLM only adds the prose.

## Run
```bash
pip install pytest
python -m pytest -q                          # 12 tests
python -m kpi_narrator                       # offline: sloppy mock draft -> caught -> repaired
ANTHROPIC_API_KEY=... python -m kpi_narrator # Claude writes, same checks
```
Replace `data/kpis.csv` (metric, unit, direction, actual, plan, prior, tolerance_pct, owner) and `data/revenue_drivers.csv` with your own month.

## Next steps
- Add a trend view (three-month slope per KPI), so "red but improving" reads differently from "red and getting worse".
- Pull the actuals straight from the warehouse with a SQL extract per KPI, and keep the plan in a versioned file.
- Post the summary to the ops channel with the variance table attached, and track which asks get owners and dates.
