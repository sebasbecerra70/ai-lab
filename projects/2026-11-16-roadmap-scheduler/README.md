# Roadmap Scheduler

Turn a list of epics, their dependencies and each team's headcount into a week-by-week plan. It finds the critical path, shows how many weeks team capacity costs you, and tells you which team to add a person to.

```text
$ npm run demo

14 epics, teams platform=3 web=2 data=2

critical path (16w with unlimited people): AUTH -> RBAC -> BILLING -> SELFSERVE -> LAUNCH
greedy priority list:      21w, 1 epic(s) late
after local search:        20w, 0 epic(s) late (4w lost to team capacity)

          |    |    |    |      target=w20
AUTH      ####...............:  w0-w4 platform
EVENTS    ####...............:  w0-w4 data
RBAC      ....###............:  w4-w7 platform
AUDIT     ....###............:  w4-w7 platform
METER     ....###............:  w4-w7 data
EXPORT    .......##..........:  w7-w9 data
ALERTS    .......##..........:  w7-w9 data
SOC2      .......##..........:  w7-w9 platform
DASH      .......###.........:  w7-w10 web
BILLING   .......#####.......:  w7-w12 platform
ADMINUI   ..........####.....:  w10-w14 web  +3w capacity wait
SELFSERVE ..............###..:  w14-w17 web  +2w capacity wait
INVOICE   .................##:  w17-w19 web  +5w capacity wait
LAUNCH    ...................#  w19-w20 web  +4w capacity wait

utilization: platform 48%, web 57%, data 38%

what if we add one person to...
  web       -> 18w (saves 2w)
  platform  -> 20w (no change)
  data      -> 20w (no change)
```

## Why it matters
Roadmap dates usually come from adding up estimates along the obvious chain of work. That number ignores the fact that the same two web engineers are needed for the admin console, the dashboard, the invoice UI and the launch. In the sample, the dependency chain alone says 16 weeks. Once team capacity is applied, the simple greedy plan takes 21 weeks and misses the week-20 enterprise launch. Re-ordering the same work with local search hits week 20 with no added headcount. The hiring what-if shows that one more web engineer saves 2 weeks, while extra platform or data engineers save nothing. That turns "we need more people" into a specific request a VP of Product can take to finance: one front-end hire, a 2-week pull-in on a $1M+ ARR tier.

This is deliberately not an LLM project. Scheduling is a constraint problem with an exact feasibility check, and a model would produce plausible-looking plans that silently break capacity.

## Architecture
```
roadmap.json ──► validate(): unknown deps/teams, epics larger than their team
                     ▼
              topoOrder() Kahn ── cycle? ──► error with path (A -> B -> C -> A)
                     ▼
              criticalPath() CPM: ES/EF/LS/LF/slack on infinite capacity = lower bound
                     ▼
              priorityList(): least LS, most downstream epics, highest value
                     ▼
              scheduleWithOrder(): serial SGS, earliest week with free team headcount
                     ▼
              schedule(): hill-climb on the list (move epic earlier, keep if cost drops)
                     │      cost = (late epics, makespan, Σ value × finish week)
                     ▼
              gantt() + utilization + hiringWhatIf() (+1 person per team, re-plan)
```
- **CPM gives the floor, list scheduling gives the plan.** Showing both makes the cost of capacity explicit (4 weeks in the sample), which is the number a PM can actually negotiate with.
- **Greedy plus local search instead of an exact solver.** Resource-constrained scheduling is NP-hard. For 10-50 epics, a priority rule plus a few hill-climbing passes runs in milliseconds and finds the obvious fixes, such as moving the invoice UI ahead of the dashboard. It needs no dependencies and is easy to explain in a planning review.
- **The objective is lexicographic on purpose.** Hitting the committed date comes first, then total length, and only then shipping high-value epics early. That matches how roadmap trade-offs are actually argued.
- **Epics are fixed-size blocks** (weeks × people). That's coarser than task-level planning, but it is the granularity roadmaps are committed at, and it keeps the schedule readable.

## Run
```bash
npm test                     # 10 tests (node:test via tsx)
npm run demo                 # schedule data/roadmap.json
npx tsx src/cli.ts my-roadmap.json
```

## Next steps
- Add estimate ranges (P50/P90) and Monte Carlo the schedule to report a date confidence instead of a single week.
- Allow epics to split across weeks (preemption) and model ramp-up for people moving between teams.
- Import epics and links straight from Jira or Linear.
