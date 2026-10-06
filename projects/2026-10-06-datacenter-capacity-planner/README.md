# Data Center Capacity Planner

Shows power, cooling and space headroom for each data hall plus site PUE, and **forecasts the month each constraint runs out** under growth scenarios, including a step load such as a GPU cluster landing.

```text
$ python -m capacity_planner
Current headroom (usable = design x 90% margin)
hall   power kW  cooling kW   racks  binding (util)
A           320         390      12  space (94%)
B           585         500      20  space (89%)
C           830         670      86  cooling (50%)
D          1760        1870      64  space (41%)
site: facility load 6260 kW of 9500 kW feed, PUE 1.36

Forecast, 36-month horizon
[conservative] first wall: hall A space in 6mo; utility feed 34mo; PUE by year [1.359, 1.349, 1.34, 1.332]
    A: power=17mo  cooling=19mo  space=6mo
    B: power=>36mo  cooling=33mo  space=12mo
    C: power=>36mo  cooling=>36mo  space=>36mo
    D: power=>36mo  cooling=>36mo  space=>36mo
[base] first wall: hall A space in 3mo; utility feed 14mo; PUE by year [1.359, 1.336, 1.319, 1.306]
    A: power=7mo  cooling=8mo  space=3mo
    B: power=16mo  cooling=14mo  space=5mo
    C: power=35mo  cooling=28mo  space=>36mo
    D: power=>36mo  cooling=>36mo  space=>36mo
[ai_cluster] first wall: hall A space in 3mo; utility feed 8mo; PUE by year [1.359, 1.327, 1.314, 1.303]
    A: power=7mo  cooling=8mo  space=3mo
    B: power=16mo  cooling=14mo  space=5mo
    C: power=35mo  cooling=28mo  space=>36mo
    D: power=27mo  cooling=26mo  space=20mo
```

## Why it matters
New capacity takes 12–24 months to deliver (utility upgrades, chillers, a new hall), so the useful question is not "how full are we?" but "when do we hit the wall, and which wall is it?" In the sample site every hall looks fine on power, yet hall A runs out of rack space in 3 months at 2.5% monthly growth. A 900 kW AI cluster in month 4 moves the **utility feed** wall from month 14 to month 8, which is shorter than the lead time for a feed upgrade. A capacity manager needs to see that before the customer signs, not after.

## Architecture
```
data/halls.csv ─┐
data/site.json ─┼─► headroom(hall, margin) ─► binding constraint + utilization
data/scenarios ─┘          │
                           ▼
            project(halls, scenario, month)    compound growth + step loads
                           │                   cooling scales with each hall's ratio
                           ▼
            forecast(): month-by-month scan ─► first month each constraint < 0
                           │                   site utility feed + PUE per year
                           ▼
                   report: headroom table + scenario walls
```
- **Usable capacity, not nameplate.** Headroom is measured against design × safety margin (90%). Running a hall at 100% of design leaves no room for failover or hot days.
- **Three walls per hall plus one per site.** Power, cooling and rack space can each be the binding constraint. A dense AI deployment usually runs out of power or cooling long before space, and a legacy hall the other way round.
- **Simulation plus a closed-form check.** The monthly scan handles step loads, which the closed form `ceil(ln(usable/load)/ln(1+g))` cannot. A test checks that the two agree when growth is pure compounding.
- **PUE follows the load.** Fixed overhead is spread over more IT load as the site grows, so PUE drifts down from 1.36 to about 1.30. That is a useful sanity check when a forecast claims an efficiency gain.
- **Why not ML?** The physics and the contracts are deterministic. The uncertainty is in the growth assumption, and explicit scenarios handle that more transparently than a fitted model would.

## Run
```bash
pip install pytest
python -m pytest -q                  # 10 tests
python -m capacity_planner           # 36-month horizon
python -m capacity_planner 60        # 5-year horizon
```
Edit `data/halls.csv`, `data/site.json` and `data/scenarios.json` to model your own site.

## Next steps
- Model N+1/2N redundancy explicitly (usable = capacity minus the largest unit) instead of a flat margin.
- Add a Monte Carlo growth rate to give a P50/P90 run-out date.
- Feed actual monthly meter readings to fit the growth rate per hall.
