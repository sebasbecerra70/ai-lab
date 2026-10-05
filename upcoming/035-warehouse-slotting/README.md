# Warehouse Slotting Optimizer

Find out which SKUs drive your pick volume (ABC velocity), reassign them to the slots that are fastest to reach, and get a phased move list that shows how much travel each batch of moves removes.

```text
$ python -m slotting
60 SKUs, 500 orders, 1234 pick lines

ABC velocity
  A: 22 SKUs ( 37%) -> 80.6% of picks
  B: 22 SKUs ( 37%) -> 14.5% of picks
  C: 16 SKUs ( 27%) ->  4.9% of picks

slotting        hours  s/order  s/line
current           7.0     50.6    20.5
optimized         2.1     15.3     6.2
travel reduction: 69.7%

60 moves for the full re-slot; phased plan:
  top  5 moves -> 38.0% less travel
  top 10 moves -> 44.4% less travel
  top 20 moves -> 53.0% less travel
  top 60 moves -> 69.7% less travel

first moves:
  SKU-1045 [A] 237 picks  A3-B2-L2 -> A0-B0-L1
  SKU-1030 [A] 125 picks  A5-B4-L1 -> A0-B0-L0
  SKU-1012 [A] 115 picks  A3-B9-L1 -> A0-B1-L1
  SKU-1013 [A]  79 picks  A3-B5-L1 -> A0-B0-L2
  SKU-1057 [A]  40 picks  A4-B7-L2 -> A0-B1-L2
```

## Why it matters
Walking is 50-60% of a picker's time in a typical piece-pick operation. Slotting decays as the assortment changes, so after a year the fast movers are scattered across the building. With 12 full-time pickers at $24/hour fully loaded, every 10% of travel removed is worth about $30k a year, before counting the throughput gain at peak. The sample uses a random baseline, so the full 70% figure overstates what you'd see in a real facility, where 20-35% is typical. The important number is the phased plan: **the top 10 moves give about 60% of the total benefit**. A supervisor can do those 10 moves on a Saturday morning without a full re-slot project.

## Architecture
```
order_lines.csv ──► pick_velocity()  (lines per SKU)  ──► abc_classes() 80/95 cuts
skus.csv  (cube S/M/L)                    │
                                          ▼
Layout (aisles × bays × levels) ──► slot_cost(): round-trip walk + level handling penalty
                                          │
                                          ▼
                 assign_slots(): fastest SKU → cheapest compatible slot (L only on floor)
                                          │
current_slots.csv ──► evaluate(): replay every order with return routing ◄── target
                                          │
                                          ▼
          prioritized_moves(): picks × slot-cost delta → apply_top_moves(k) → phased curve
```
- **Velocity is measured in pick lines, not units**, because each line is one trip to the slot no matter how many units are picked.
- **Greedy matching** (sorted SKUs to sorted slots) is provably optimal for single-line picking with identical slots. Cube constraints make it a heuristic here, but a very good one at this scale.
- **Evaluation replays real orders** with a return-routing walk model, instead of trusting the per-slot cost. This catches multi-line orders that benefit from co-location.
- **Moves are the unit of work.** Re-slotting has labor cost and disruption risk, so the output is a ranked move list with diminishing returns, not just a final layout.
- **No ML or LLM needed.** This is combinatorial optimization on known data, and every number can be traced back to an order line.

## Run
```bash
pip install pytest
python -m pytest -q      # 10 tests
python -m slotting
```

## Next steps
- Add SKU affinity (items often picked together) and place pairs in adjacent bays.
- Model S-shape routing and batch picking, and compare them with return routing.
- Add seasonal re-slot triggers: alert when an SKU's velocity class has changed for 3 consecutive weeks.
