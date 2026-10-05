# Discount Approval Agent

A deal desk agent for discount requests. It applies the approval policy, routes escalations (pricing ladder, margin floors, precedent, Legal and Finance terms) and proposes give-gets that lower the approval level. It prices the trade-off with a win-rate model, and has an LLM draft the approver memo, which is checked number by number before anyone reads it.

```text
$ python -m deal_desk
win model: 242 closed deals, log loss 0.627 (base rate 47%); p(win) mid-market, no competitor: 0% -> 40%, 10% -> 51%, 20% -> 56%, 30% -> 54%, 40% -> 45%

== Q-1041 Brightline Logistics: 8% on $120,000 list -> AUTO-APPROVE (AE)
   effective 5% after annual prepay -3; margin 86%; net ARR $110,400
   memo ok: Brightline Logistics (Q-1041) requests 8% off $120,000 list ARR, for $110,400 net ARR over 1 year(s). Gross ma...

== Q-1042 Kestrel Health: 24% on $450,000 list -> ESCALATE (Sales Manager)
   effective 14% after 3-year term -5, annual prepay -3, displacing Datadog -2; margin 83%; net ARR $342,000
   > AE can approve 20% on the current terms ($18,000 more net ARR a year)
   win model: 29% at 24% vs 29% at 20%; expected ARR $99,699 vs $105,190
   memo ok: Kestrel Health (Q-1042) requests 24% off $450,000 list ARR, for $342,000 net ARR over 3 year(s). Gross margin ...

== Q-1043 Orion Retail Group: 35% on $1,008,000 list -> ESCALATE (CFO, Finance, Legal)
   effective 33% after displacing Snowflake -2; margin 65%; net ARR $655,200
   ! large deal: net ARR $655,200 is at or above $500,000 -> VP Sales
   ! margin floor: gross margin 65% is below the 70% floor -> CFO
   ! non-standard: net-90: cash cycle beyond net-45 standard -> Finance
   ! non-standard: MFN: most-favored-nation pricing constrains every future deal -> Legal
   > VP Sales can approve 24% on the current terms ($110,880 more net ARR a year)
   win model: 25% at 35% vs 29% at 24%; expected ARR $161,150 vs $223,326
   memo ok: Orion Retail Group (Q-1043) requests 35% off $1,008,000 list ARR, for $655,200 net ARR over 1 year(s). Gross m...

== Q-1044 Pinecrest Credit Union: 18% on $25,200 list -> ESCALATE (Sales Manager)
   effective 18%; margin 72%; net ARR $20,664
   > with a 3-year term with annual prepay, 18% needs only AE
   > AE can approve 10% on the current terms ($2,016 more net ARR a year)
   win model: 72% at 18% vs 68% at 10%; expected ARR $14,791 vs $15,438
   memo REJECTED (number not in facts: 84), template memo used

== Q-1045 Vantage Freight: 45% on $126,000 list -> REJECT (CFO, Legal)
   effective 43% after displacing Looker -2; margin 59%; net ARR $69,300
   ! margin floor: gross margin 59% is below the 70% floor -> CFO
   ! non-standard: uncapped liability: liability cap is non-negotiable below 2x fees -> Legal  [BLOCKING]
   win model: 18% at 45% vs 31% at 24%; expected ARR $12,543 vs $30,057
   memo ok: Vantage Freight (Q-1045) requests 45% off $126,000 list ARR, for $69,300 net ARR over 2 year(s). Gross margin ...

== Q-1046 Northwind Labs: 22% on $180,000 list -> ESCALATE (VP Sales)
   effective 22%; margin 84%; net ARR $140,400
   ! precedent: 22% vs 9% on the last deal with this customer; the next renewal will anchor on it -> Sales Manager
   > with a 3-year term, 22% needs only Sales Manager
   > with annual prepay, 22% needs only Sales Manager
   > Sales Manager can approve 20% on the current terms ($3,600 more net ARR a year)
   win model: 56% at 22% vs 56% at 20%; expected ARR $78,693 vs $80,577
   memo ok: Northwind Labs (Q-1046) requests 22% off $180,000 list ARR, for $140,400 net ARR over 1 year(s). Gross margin ...

auto-approve: 1, escalate: 4, reject: 1; discount requested $571,236/yr
```

## Why it matters
Discount approvals are where B2B margin quietly disappears. Reps ask for the maximum because escalation is slow, managers approve because they can't see the precedent or the margin, and every deal becomes the anchor for the next renewal. In this book of six quotes, $571k a year of discount is on the table. The agent auto-approves the clean renewal in seconds and rejects the uncapped-liability deal outright. For the others it shows the cheaper path:
- **Orion Retail**: the CFO, Finance and Legal all have to sign 35%. At 24% the pricing approval drops to the VP Sales (MFN and net-90 still go to Legal and Finance). That is $110,880 more net ARR a year, and the win model doesn't think 35% helps anyway (25% vs 29%).
- **Pinecrest**: 18% needs a Sales Manager today, or only the AE if the customer accepts a 3-year term with annual prepay. That is a give-get the rep can offer on the call.
- **Northwind**: 22% against 9% last year sets an anchor for the next renewal. The agent flags it before it becomes the new baseline.

The win model is the honest part. On 240 closed deals, discount helps up to about 20% and then stops buying wins (56% at 20%, 45% at 40%). Deep discounts tend to show up in procurement-led deals that were going to be hard anyway.

## Architecture
```
data/deals.json ─┐
data/policy.json ┼─► evaluate(): allowances (3-yr, prepay, displacement) ─► effective discount ─► ladder role
data/history.csv ┘        │      large deal, margin floor / hard floor, term length, precedent ─► raise role
                          │      non-standard terms ─► side approvers (Legal, Finance) or BLOCK
                          │      give_gets(): re-run the whole rulebook with other terms / lower discounts
                          ▼
             winrate.fit(): logistic regression from scratch on discount, discount², competitor, segment
                          │      p(win) and expected ARR at the request vs the lower-level counter
                          ▼
             build_facts() ─► LLMClient.complete()   MockLLM (template) | AnthropicLLM (stdlib HTTP)
                          ▼
             verify_memo(): every number must come from the facts, every approver and the decision stated
                          │      fails ─► plain template memo, issue logged
                          ▼
                       CLI report
```
- **Rules decide and the LLM writes.** The decision, approvers and give-gets come from deterministic code that finance can audit. The model gets a FACTS block and drafts prose. If it says "auto-approve" on a rejected deal, or quotes an 84% margin that is really 72%, the memo is discarded, not obeyed. A test sends a memo that tries to approve the uncapped-liability deal and checks that it is caught.
- **Give-gets re-run every rule.** A naive "3-year term drops you one level" is wrong when the margin floor or the large-deal rule is what drives the escalation. Orion is the test case: no term give-get is offered, because a CFO is still needed.
- **Allowances encode what terms are worth.** Three years earns 5 points, prepay 3, and a competitive displacement 2. That makes the ladder about economics instead of raw percentages. The values live in `policy.json`, owned by revenue operations.
- **Why logistic regression?** 240 rows, a handful of features and a need to explain the curve to a CRO. A squared discount term lets the model show saturation, which is the whole argument. Gradient descent is written from scratch (standard library only), and log loss is checked against the base rate in tests.
- **Precedent from history.** The last discount won with the customer comes from `history.csv`, a stand-in for the CRM. Jumps of more than 10 points are escalated, because renewals anchor on them.

## Run
```bash
pip install pytest
python -m pytest -q                         # 11 tests
python -m deal_desk                         # sample book, offline mock LLM
ANTHROPIC_API_KEY=... python -m deal_desk   # memos drafted by Claude, same verification
```

## Next steps
- Post the decision to the CRM quote and request approvals in Slack with one-click approve or deny, logging the reasons.
- Fit win rate per segment with more history, and add sales cycle length: deep discounts that don't raise win rate might still close deals faster.
- Track approval SLA and the share of discount granted above the AE level per rep, which feeds sales coaching.
