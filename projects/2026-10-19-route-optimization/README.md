# Delivery Route Optimizer

Plans daily delivery routes from one DC to 32 stores under truck capacity and driver-shift limits. It uses the Clarke-Wright savings heuristic plus 2-opt, compared against the "nearest next stop" logic a dispatcher would use by hand.

```text
$ python -m routing
32 stops, 83 pallets, trucks of 18 pallets, max 110 km/route (lower bound 5 trucks)

method          trucks      km  cost/day  feasible
nearest              5   334.2     1,818  yes
nearest+2opt         5   331.7     1,814  yes
savings              5   254.1     1,670  yes
savings+2opt         5   253.2     1,668  yes

savings vs nearest-neighbour: 81.0 km and $150/day (~$37,450/yr over 250 days)

truck 1: 17/18 pallets  59.1 km  DC -> S04 -> S03 -> S06 -> S02 -> S01 -> S05 -> DC
truck 2: 18/18 pallets  53.2 km  DC -> S09 -> S08 -> S11 -> S12 -> S13 -> S07 -> S10 -> S30 -> DC
truck 3: 17/18 pallets  68.9 km  DC -> S14 -> S18 -> S17 -> S15 -> S19 -> S16 -> S29 -> DC
truck 4: 17/18 pallets  43.3 km  DC -> S22 -> S23 -> S25 -> S24 -> S20 -> S26 -> S21 -> DC
truck 5: 14/18 pallets  28.8 km  DC -> S32 -> S31 -> S27 -> S28 -> DC

$ python -m routing 12 70        # smaller box trucks, shorter shifts
nearest              9   483.6     3,055  yes
savings+2opt         7   357.7     2,342  yes
savings vs nearest-neighbour: 125.9 km and $713/day (~$178,223/yr over 250 days)
```

## Why it matters
Last-mile delivery is often the biggest line in a distribution budget, and most of it comes down to two numbers: **trucks dispatched** and **kilometres driven**. A greedy "go to the closest store that fits" plan looks sensible on a map, but it strands far-away stores and ends routes with long empty runs back to the DC.

On the sample network, savings plus 2-opt cuts 24% of the kilometres with the same five trucks. With smaller trucks and shorter shifts it also removes **two whole routes** (9 → 7), about $178k a year at $240 per driver-day plus $1.85/km. Those cost inputs are constants at the top of the CLI, so an ops manager can put in their own rates.

## Architecture
```
data/stops.csv (x/y km, pallets) ──► Problem(depot, stops, capacity, max_route_km)
                                          │
              ┌───────────────────────────┼─────────────────────────────┐
              ▼                           ▼                             ▼
     nearest_neighbour()           clarke_wright()                       │
     (baseline dispatcher)         savings s(i,j)=d0i+d0j−dij, merge     │
              │                    route ends while capacity/km allow    │
              └─────────► two_opt() per route: reverse segments while shorter
                                          ▼
                     Solution(routes, km, trucks) ──► check(): each stop once, capacity, km limit
```
- **Clarke-Wright parallel savings.** This is the classic construction heuristic. Start with one out-and-back trip per stop, then link the pairs that save the most distance, but only at route ends, and only if capacity and shift length still hold. It's simple, deterministic, and usually within 5–10% of optimal on problems this size.
- **2-opt as a separate pass.** It removes crossing edges inside each route. It adds little after savings (which already builds tidy routes) and more after the greedy baseline. Both combinations are shown so the effect of each piece is visible.
- **Hard constraints in one place.** Capacity and max route km are checked during construction, and `check()` re-verifies the final plan independently. A bug in a heuristic shows up as "infeasible", never as a quietly wrong plan.
- **Road factor.** Straight-line km × 1.3 is a standard metro approximation. The `dist()` function is the single seam to swap in a real distance matrix (OSRM, Google, HERE).
- **Why heuristics and not a solver:** standard library only, under 50 ms, and explainable to a dispatcher. For 30–200 stops, savings + local search is what many commercial TMS tools ship as their default.

## Run
```bash
python -m pytest -q          # 13 tests
python -m routing            # 18-pallet trucks, 110 km shift limit
python -m routing 12 70      # smaller trucks, shorter routes
```

## Next steps
- Add delivery time windows (VRPTW) and service time per stop.
- Add inter-route moves (relocate, swap / Or-opt) to rebalance loads between trucks.
- Use a real road distance matrix and drive times per time-of-day.
- Allow a heterogeneous fleet (box trucks vs 53' trailers) with different costs.
