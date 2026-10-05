# Rack Placement Optimizer

Places a deployment wave of servers into data center racks without breaking power budgets, U-space or redundancy rules, and leaves as many racks empty as possible for the next wave.

```text
$ python -m rack_placement
47 servers (67U, 40.0 kW) into 15 racks across rows R1, R2, R3

strategy               racks  new unplaced  stranded kW  stranded U  peak util
first_fit                 12    8        0         0.00          59      100%
first_fit+drain           10    6        0         0.00          60      100%
best_fit                  12    8        0         0.00          59      100%
best_fit+drain            10    6        0         0.00          60      100%
worst_fit                 15   11        0         0.00           0       71%
lower bound                8

plan: first_fit+drain  (constraint violations: 0)
  R1-01  34/38U   8.5/8.6 kW  ceph-01, db-orders-01, kafka-01
  R1-02  27/38U   8.6/8.6 kW  gpu-01, db-users-01
  R1-04   7/38U   3.3/8.6 kW  ceph-04, ci-08, web-checkout-01, web-search-01, redis-01, kafka-02
  ...
  R3-03   4/38U   1.9/8.6 kW  web-checkout-06, web-search-06, ceph-07
  left empty for future demand: R1-03, R2-04, R2-05, R3-04, R3-05
```

## Why it matters
Rack placement is usually done in a spreadsheet by whoever runs the install, and the mistakes are expensive. If two database replicas land in the same rack, one PDU trip takes out the service. If a GPU node goes into a rack that's already at 80% power, it trips a breaker on its first training job. And if a 4 kW rack is half empty but out of power, that space is stranded and can't be sold or used.

In this sample wave the naive "fill in order" approach uses 12 racks. The consolidation pass gets that to 10 with zero rule violations, which leaves 5 of 15 racks free instead of 3. In a colo cage at about $1,500 per rack per month, two extra free racks are worth about $36k a year, or they're the room the next GPU order needs without a new contract. The stranded-U column also tells a capacity manager something useful: with power-dense hardware, power runs out long before space does, so asking for more racks is the wrong request. The real ask is more kW per rack.

## Architecture
```
data/racks.csv ─┐        ┌───────────── Placer ──────────────┐
(row, U, kW,    ├──────► │ order: dominant size desc,        │
 brownfield)    │        │        grouped items first        │
data/servers.csv┘        │ for each server: legal racks =    │──► Plan ──► evaluate()  racks, stranded kW/U, lower bound
(U, kW, group)           │   U fits ∧ kW fits ∧ no replica   │       └──► validate()  independent constraint re-check
                         │   in rack ∧ row quota not full    │
                         │ choose: first / best / worst fit  │
                         │ consolidate: drain lightest racks │
                         └───────────────────────────────────┘
```
- **Dominant-resource sizing.** Servers are sorted by their largest share of a rack (U or kW). A 4U GPU node at 3.4 kW is "big" because of power, not space, and sorting by U alone would place it badly.
- **Hard constraints in one function.** `violation()` returns the first rule a placement breaks. The same reason is reported for unplaced servers, so the output says "power", not "no fit".
- **Redundancy as two rules.** Anti-affinity means no two replicas share a rack. Row spread means at most ceil(n / rows) replicas per row, so losing a row's PDU or cooling zone degrades a service but never kills it.
- **Per-feed power budget.** Rack kW is the 80%-derated budget of a single feed, so a 2N rack still holds its load if one feed is lost.
- **Prefer powered racks.** Opening an empty rack is the real cost, so best-fit only looks at greenfield racks when no in-use rack is legal.
- **Consolidation pass.** After packing, it tries to move every server out of the lightest greenfield rack into the others. If any server can't move, the attempt rolls back. This simple local search is what turns 12 racks into 10.
- **Why heuristics, not an ILP solver:** standard library only, it runs in milliseconds, and every decision can be explained to the install team. The `lower bound` row (max of U, kW and largest replica group) shows how close the heuristic gets. Here it's 10 racks against a bound of 8, and the bound itself is optimistic.

## Run
```bash
python -m pytest -q                 # 14 tests
python -m rack_placement            # compare strategies, print the best plan
python -m rack_placement worst_fit  # spread for thermal balance instead
```

## Next steps
- Add per-row cooling (kW per row) and per-rack weight limits as more constraints.
- Model rack position within a row so the heaviest racks sit nearest the CRAH units.
- Swap the drain pass for simulated annealing and measure the gap to the lower bound.
- Export a cabling and install sheet (rack, U position, PDU outlet) for the remote-hands team.
