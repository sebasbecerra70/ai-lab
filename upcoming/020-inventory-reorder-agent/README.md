# Inventory Reorder Agent

An MRO storeroom buyer's assistant. It computes safety stock, reorder points and EOQ for every SKU, proposes purchase orders, tops up orders that fall below a supplier minimum, flags lines that need expediting, and **routes each PO by approval threshold**. An LLM writes the approver memo, and a check rejects any memo that contains numbers not in the facts.

```text
$ python -m reorder_agent
sku        position  safety    ROP    EOQ  cover d  LT d  status
FLT-2010        120      36    150    278     12.6    12  REORDER
BRG-6205        760     399   1197   1310     20.0    21  REORDER
BRG-6308         35      68    198    328      5.6    21  REORDER
GLV-NIT-L       180      42    152    405      8.2     5
MTR-5HP           3       6     18     11      8.6    35  REORDER
SGL-CLR          20       7     22    323      6.7     5  REORDER
...
proposed POs (MockLLM memos):

Motion Industrial: $34,234.50 -> pending director
  BRG-6205    1750 x $4.85    = $ 8,487.50  position 760 <= ROP 1197  [EXPEDITE]
  BRG-6308     500 x $12.60   = $ 6,300.00  position 35 <= ROP 198  [EXPEDITE]
  BLT-A42      370 x $7.90    = $ 2,923.00  position 95 <= ROP 122
  MTR-5HP       27 x $612.00  = $16,524.00  position 3 <= ROP 18  [EXPEDITE]
  ! expedite: BRG-6205, BRG-6308, MTR-5HP will run out before a standard delivery
  memo: Expedite BRG-6205, BRG-6308, MTR-5HP: stock on hand and on order covers 20.0 days against a 21-day lead time. ...

Safety First: $4,723.60 -> submitted
  SGL-CLR      336 x $2.10    = $   705.60  position 20 <= ROP 22
  GLV-NIT-L    410 x $9.80    = $ 4,018.00  pulled forward: reaches ROP in 1.3 days

auto-submitted $7,013.20; awaiting approval $45,645.30; on hold 0 PO(s)
```

## Why it matters
In a plant storeroom, one missing $12 bearing can stop a production line that earns thousands of dollars an hour. Over-ordering, meanwhile, ties up working capital in shelves of slow movers. Most storerooms run on min/max levels someone set years ago. This agent re-derives them from current demand and lead-time variability: reorder points cover a stated service level (95–98%), and order sizes balance PO admin cost against carrying cost (EOQ).

The approval routing is where the "agent" earns trust. POs up to $5k are submitted automatically, which is most day-to-day volume (gloves, glasses, grease). The $34k Motion Industrial order with a $16.5k motor line goes to a director, and the memo puts the expedite risk first. The Safety First order would have been $706, below the $1,000 supplier minimum, so the agent pulls forward gloves that hit their reorder point in 1.3 days instead of paying a small-order fee or waiting. Buyers spend their time on the exceptions, not on typing routine POs.

## Architecture
```
data/skus.csv ──► calc.py: z(service level) · safety stock = z·√(LT·σd² + d²·σLT²) · ROP = d·LT + SS · EOQ = √(2DS/H)
                       │
                       ▼
               plan_line(): position ≤ ROP → order up to ROP + EOQ, round to case pack,
                            cap at max days of supply, expedite if cover < lead time
                       │ group by supplier
                       ▼
data/policy.json ► ReorderAgent.run():
                    _top_up()      pull forward same-supplier SKUs within 30 days of ROP until the minimum is met
                    route()        auto ≤ $5k · ops_manager ≤ $25k · director above   (code, never the LLM)
                    status         submitted | pending <approver> | hold (below supplier minimum)
                    memo           LLMClient(MEMO_SYSTEM, FACTS) → ungrounded_numbers() → template fallback
```
- **Classic inventory math, not ML.** With stable MRO demand, a well-parameterized (s, S) policy beats a black box and is auditable line by line. The safety-stock formula includes lead-time variance, which usually matters more than demand variance for long-lead parts (see BRG-6205: 399 units of safety stock).
- **Policy in data, authority in code.** Thresholds and supplier minimums live in `policy.json`. The LLM can't approve, change quantities or reroute. It writes the memo and nothing else.
- **Number-grounding check on memos.** Every number in the memo must appear in the facts. If the model invents "prices rise 12% next week", the memo is replaced with a template and the PO is flagged. This check found a real gap during development (the line count wasn't in the facts), which is now fixed.
- **Pull-forward with a limit.** Topping up only considers SKUs within 30 days of their reorder point. Hitting a supplier minimum shouldn't become an excuse to buy months early.
- **Trade-off:** demand is assumed stationary and normally distributed. Intermittent spare parts (MTR-5HP, 0.35/day) would be better served by a Poisson or Croston-based policy (see the demand forecasting project).

## Run
```bash
python -m pytest -q                            # 12 tests
python -m reorder_agent                        # template memos
ANTHROPIC_API_KEY=... python -m reorder_agent  # Claude writes the memos; grounding check still applies
```

## Next steps
- Use a Poisson / service-level policy for slow-moving spares and compare stockouts in a simulation.
- Add supplier price breaks to EOQ (all-units discount).
- Write approved POs to the ERP and learn actual lead times from receipts to refresh σLT.
- Add a Slack approval flow for pending POs with the memo and a one-click approve.
