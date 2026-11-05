# Energy-Aware Job Scheduler

Shift flexible batch work (training runs, backups, transcodes) into the cheapest or lowest-carbon hours of a 48-hour grid forecast, without breaking deadlines or the facility's power headroom.

```text
$ python -m energy_scheduler
12 jobs, 48h horizon, cap 900 kW, carbon price $100/t

plan         cost $   CO2 kg  peak kW  deadlines
asap            711     4895      830  met
optimized       577     4109      880  met
savings: 18.8% cost, 16.1% carbon

hour              |012345678901234567890123456789012345678901234567|
etl-nightly       |###.......                                      |
ml-train-recsys   |...........######.............                  |
backup-full       |............####........                        |
report-finance    |      .#.                                       |
ml-train-fraud    |  .................................#####        |
video-transcode   |..........#............######.....#...........  |
index-rebuild     |          ...##.....                            |
log-compaction    |.............##........................#........|
genomics-batch    |    .......#....#..........##.....######........|
cache-warm        |                    ...#                        |
analytics-weekly  |            ####....................            |
sim-capacity      |        ....#..#...................####.....    |

carbon price $/t -> cost $, CO2 kg
     0 ->     569,    4293
    50 ->     572,    4188
   100 ->     577,    4109
   200 ->     595,    3977
   500 ->     606,    3939
```

## Why it matters
A site running 2-3 MW of deferrable batch work at $60/MWh spends about $1.2M a year on that energy. Wholesale and time-of-use prices regularly swing 2-3x within a day: the solar trough at midday is cheap and the evening ramp is expensive. Grid carbon intensity moves the same way. In the sample, simply honoring each job's real deadline instead of running everything at release saves about 19% on cost and 16% on CO2, with every deadline still met. For a data center manager, that's a budget line and a sustainability-report line at once. It also turns a vague "be greener" ask into a dial: the shadow carbon price.

## Architecture
```
data/jobs.csv  (power, duration, release, deadline, preemptible)
data/grid_48h.csv  (hourly $/MWh, gCO2/kWh forecast)
        │
        ▼
hour_score = price + carbon_price × tCO2/MWh
        │
        ▼
schedule_optimized(cap_kw)
  sort by slack (least flexible first), then energy
  ├─ non-preemptible → cheapest contiguous window that fits under cap
  └─ preemptible     → cheapest N individual hours that fit under cap
        │
        ▼
evaluate()  cost $, CO2 kg, peak kW, deadline check   vs.  schedule_asap() baseline
tradeoff_curve()  sweep carbon price 0 → 500 $/t
```
- **Why not an LLM?** This is a constrained optimization problem with exact numbers. A deterministic heuristic is auditable, reproducible, and runs in milliseconds. An LLM adds nothing here and could break hard constraints.
- **Greedy by slack** is a well-known heuristic for deadline scheduling. It isn't globally optimal under tight capacity (that would need a MILP), but it's always feasible-checked, and the gap is small when headroom is reasonable.
- **One objective, one knob.** Folding carbon into a shadow price ($/t) makes cost vs. carbon a single business decision. The trade-off curve shows that at $200/t, CO2 falls a further 7% for about $26 more on this workload.
- **Hard constraints are validated after scheduling** (`deadlines_met`, contiguity, peak under cap), so a bug in the heuristic can't quietly produce an unsafe plan.

## Run
```bash
pip install pytest
python -m pytest -q                                    # 9 tests
python -m energy_scheduler --cap-kw 900 --carbon-price 100
```

## Next steps
- Replace the greedy pass with a small local-search improvement step, and benchmark it against an exact solver on small cases.
- Pull real day-ahead prices and marginal carbon intensity (e.g., an ISO feed) instead of the synthetic duck curve.
- Add cooling overhead (hourly PUE driven by outdoor temperature), so hot afternoons cost more per IT kWh.
