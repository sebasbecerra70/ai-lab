# Safety Stock Calculator

Set safety stock and reorder points per SKU when both customer demand and supplier lead time vary. The tool reports how much of each SKU's risk comes from the supplier, prices the service-level trade-off curve, and checks the formulas with a Monte Carlo simulation of the actual reorder policy.

```text
$ python -m safety_stock
8 SKUs, 52 weeks of demand, 10 receipts each; cycle-service targets {'A': 0.98, 'B': 0.95, 'C': 0.9}

sku      abc   d/wk  sd_d  LT wk sd_LT  LT var  SS naive     SS    ROP SS fill99     SS $  simulated CSL
PMP-100  A       40     9    3.0   0.2     23%        32     36    157        16   11,157  96.2% -> 97.8%
VLV-220  A      196    61    1.9   0.3     32%       176    214    595       109    8,134  95.3% -> 97.4%
FLT-310  B       90    40    3.9   0.9     49%       130    182    535       155    3,994  86.6% -> 92.6%
SNS-410  A       31    21    6.4   1.9     54%       111    164    366       142   23,729  91.4% -> 97.1%
GSK-500  C      261    89    1.4   0.2     15%       135    146    514        85      584  86.8% -> 88.6%
MTR-620  B       12     8    7.5   2.0     53%        38     55    148        62   37,906  87.2% -> 95.1%
BRG-710  C      382    78    2.6   0.7     83%       161    391   1374       343    1,174  74.2% -> 89.6%
CBL-800  B       55    33    2.9   1.0     50%        92    130    292       124   15,644  85.2% -> 92.9%

'SS naive' ignores lead-time variability; 'LT var' = share of lead-time demand variance from the supplier.
simulated CSL: 5,000 weeks of gamma demand and lead times, naive SS -> full SS.

service level vs safety stock investment (all SKUs at one cycle-service level)
   80.0%  $   48,227  ############
   90.0%  $   73,437  ##################  +$25,209
   95.0%  $   94,255  #######################  +$20,818
   98.0%  $  117,686  #############################  +$23,431
   99.0%  $  133,307  #################################  +$15,621
   99.5%  $  147,603  ####################################  +$14,296
   99.9%  $  177,080  ############################################  +$29,477

flat 98% on every SKU: $117,686   ABC-tiered 98%/95%/90%: $102,322  (saves $15,364)
```

## Why it matters
The common spreadsheet formula, `z × σ_demand × √LT`, assumes the supplier always delivers on time. When lead times vary, it underprotects without anyone noticing. In the sample, the bearing BRG-710 gets 74% service against a 90% target with the naive formula, because 83% of its lead-time demand variance comes from the supplier. Two practical consequences follow. First, a planner can see that the fix for BRG-710 is a supplier conversation (cut lead-time variability) rather than more inventory. Second, finance can see the price of service. Going from 99% to 99.9% across these 8 SKUs costs about $29k more in safety stock than going from 98% to 99% (about $16k). ABC-tiered targets save about $15k against a flat 98% at the same service on A items. Across a 5,000-SKU distribution center, those percentages are seven-figure working-capital decisions.

This is classic operations research, not an LLM problem. The answers are closed-form, auditable and have to be exact.

## Architecture
```
demand.csv (52 weeks)   receipts.csv (actual PO lead times)   skus.csv (cost, Q, ABC)
          └───────────────────────┬──────────────────────────────┘
                                  ▼
  Sku: d, σd, LT, σLT  →  σ_LTD = √(LT·σd² + d²·σLT²),  lt_share = d²σLT² / σ_LTD²
                                  ▼
  safety_stock_csl():  z(CSL) × σ_LTD                 (cycle service: P[no stockout per cycle])
  safety_stock_fill(): solve σ_LTD·G(z) = (1−fill)·Q  (fill rate via the normal loss function)
  reorder_point():     d·LT + SS
                                  ▼
  tradeoff_curve(): $ in safety stock per service level, marginal cost per step
  portfolio_value(): flat vs ABC-tiered targets
                                  ▼
  simulate(): daily (ROP, Q) policy on inventory position, gamma demand and lead times,
              multiple orders in flight → achieved CSL and fill rate
```
- **Two service definitions, deliberately.** Cycle service (no stockout per cycle) is what planners quote. Fill rate (share of units shipped from stock) is what customers feel. Fill-rate safety stock falls as order quantity grows, which a CSL-only tool would miss.
- **The standard library is enough.** The inverse normal and the inverse loss function are solved by bisection on `math.erf`. That's exact to 1e-10 and adds no dependencies.
- **Simulation checks the formula.** The policy runs on inventory position with orders allowed to cross, and gamma draws give non-negative, skewed demand and lead times. Achieved CSL lands within 1-3 points of target. The remaining gap is the known bias of the normal approximation for skewed, lumpy items such as MTR-620 and FLT-310, which is useful to know before trusting the formula on long-tail SKUs.

## Run
```bash
pip install pytest
python -m pytest -q             # 10 tests
python -m safety_stock          # sample: 8 industrial MRO SKUs
python -m safety_stock my_data/ # skus.csv, demand.csv, receipts.csv
```

## Next steps
- Use empirical lead-time-demand quantiles (bootstrap from history) for lumpy SKUs where the normal approximation is weakest.
- Add a review-period (periodic review) mode: σ over LT + R instead of LT.
- Optimize service targets per SKU against stockout cost (margin × lost-sale probability) instead of fixed ABC tiers.
