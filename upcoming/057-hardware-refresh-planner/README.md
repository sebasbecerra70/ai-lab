# Hardware Refresh Planner

A server lifecycle and TCO model that decides which cohorts to refresh each year under a capex budget. It weighs energy, post-warranty maintenance, wear-out failures and consolidation against capex, and it knows when to **wait for the next platform generation**.

```text
$ python -m refresh_planner
Fleet: 2110 servers in 12 cohorts, run cost $3.63M/yr
Per-server run cost, 7-year-old gen3 vs new gen6: energy $587/$908, license $450/$450, space $240/$240, maintenance $503/$0, failures $110/$33

TCO-optimized plan
Year 1: spend $1.74M of $2.20M
   web-a         320 ->  88 gen6  capex  $1.25M  NPV  $1.10M  (positive NPV)
   db-a           64 ->  18 gen6  capex   $255k  NPV   $211k  (positive NPV)
   analytics-a    60 ->  17 gen6  capex   $241k  NPV   $202k  (positive NPV)
Year 2: spend $1.92M of $2.00M
   batch-a       300 -> 138 gen6  capex  $1.92M  NPV    $32k  (positive NPV)
   waiting for next platform: web-b, storage-a, ci-a
Year 3: spend $1.74M of $2.00M
   batch-a       100 ->  31 gen7  capex   $515k  NPV   $303k  (end of support)
   storage-a      90 ->  28 gen7  capex   $465k  NPV   $236k  (positive NPV)
   ci-a          150 ->  46 gen7  capex   $764k  NPV   $357k  (positive NPV)
Year 4: spend $1.58M of $1.80M
   cache-a       120 ->  37 gen7  capex   $615k  NPV   $281k  (end of support)
   web-b         187 ->  58 gen7  capex   $964k  NPV   $404k  (positive NPV)
Year 5: spend $482k of $1.80M
   web-b          93 ->  29 gen7  capex   $482k  NPV   $266k  (end of support)

Policy comparison over 5 years (capacity held constant)
policy           PV cost  PV cash   capex  exit run-rate  servers  past warranty
run-to-EOS       $15.20M  $18.25M  $6.93M      $2.08M/yr     1055            626
5-year age       $15.21M  $18.43M  $9.10M      $1.94M/yr     1011            420
TCO-optimized    $15.04M  $17.50M  $7.47M      $2.22M/yr     1114            626
(PV cost = opex + straight-line depreciation of new hardware; PV cash = opex + capex as paid)

TCO-optimized vs 5-year age rule: PV cost -$171k, capex -$1.63M, exit run-rate $277k/yr
over budget: run-to-EOS year 3, run-to-EOS year 5
```

## Why it matters
Most fleets refresh on a fixed age rule ("anything at 5 years goes"), because it is easy to defend in a budget meeting. It also spends money in the wrong places. A 3-year-old gen5 cohort is still cheap to run, while a 7-year-old gen3 cohort burns $503 a year per server in out-of-warranty maintenance and consolidates almost 4:1 onto new hardware. On this sample 2,110-server fleet, the TCO plan meets the same capacity with **$1.63M less capex** and $171k lower present cost than the 5-year rule, and it stays inside every annual budget. Run-to-end-of-support breaks the budget in years 3 and 5, because everything comes due at once.

The plan also shows the trade-off honestly. It leaves more servers past warranty and a higher run rate at exit ($2.22M vs $1.94M a year), because it is still running gen5 hardware that is economic to keep. That is the conversation a DC operations lead should have with finance, with the numbers in front of them.

## Architecture
```
data/fleet.csv ──────┐  cohorts: servers, age, perf, watts, warranty
data/assumptions ────┤  power price, PUE, licenses, maintenance curve, AFR curve,
                     │  migration/salvage, platform roadmap, annual budgets
                     ▼
   server_opex(age)  energy + license + space + post-warranty maintenance + AFR x cost/failure
                     │
   window_cost(cohort, year, refresh_at)   PV of running this capacity for 5 years,
                     │                     refreshing at year t onto the newest platform
                     ▼
   npv_of_refresh(delay=0) vs npv_of_refresh(delay=1)  ─► refresh now / wait for next gen / keep
                     │
   run(policy): each year
     1. end-of-support cohorts are mandatory
     2. policy spends the rest:  TCO = 0/1 knapsack DP over 100-server tranches (max NPV)
                                 age = oldest first, age >= 5   |   run-to-EOS = nothing
     3. pay opex, depreciate capex, age the fleet
                     ▼
   year plan + policy comparison (PV cost, PV cash, exit run-rate, past-warranty servers)
```
- **Capacity is held constant.** Refreshes are like-for-like on benchmark performance (`ceil(servers x perf_old / perf_new)`), so every policy delivers the same compute and the comparison is purely cost. A test checks capacity per role after every policy.
- **Waiting is a real option.** When a new generation is one year out, the planner compares refreshing now with refreshing next year, over the same window. In year 2 it holds web-b, storage-a and ci-a for gen7 (50% more perf for 11% more watts). It never defers a cohort into its forced end-of-support year, because that only piles capex onto next year's budget.
- **The comparison uses depreciation, not cash.** Over a fixed horizon, any policy that buys late looks cheap in cash terms. PV cost charges capex straight-line over the platform's life, and PV cash is shown next to it so finance can see both.
- **Tranches and knapsack.** Big cohorts are split into tranches of up to 100 servers, so a 400-server batch cluster can migrate over two years. A 0/1 knapsack (DP in $10k units, checked against brute force in tests) picks the highest-NPV set that fits.
- **Why not ML?** Failure rates and maintenance curves are well-known engineering inputs, and the decision is an optimization with explicit trade-offs. A deterministic model that finance can audit line by line beats a black box here. AFR is the one input worth fitting from ticket history (see next steps).
- **Myopic by design.** Each year is optimized given the fleet and the roadmap. A full multi-year MIP could do slightly better, but the year-by-year plan matches how budgets are actually approved.

## Run
```bash
pip install pytest
python -m pytest -q                       # 12 tests
python -m refresh_planner                 # TCO-optimized plan + policy comparison
python -m refresh_planner "5-year age"    # show the age-rule plan instead
```
Edit `data/fleet.csv` and `data/assumptions.json` (budgets, power price, roadmap) to model your own fleet.

## Next steps
- Fit the AFR curve per platform from hardware ticket history instead of assuming one wear-out rate.
- Add power and space as constraints: a refresh that frees 40 kW in a power-bound hall is worth more than its opex saving.
- Run a Monte Carlo over power price and roadmap slip to see how robust "wait for gen7" is.
