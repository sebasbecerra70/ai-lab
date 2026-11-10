# SLA Error Budget Calculator

Turn an availability target into concrete numbers (allowed downtime, error budget remaining, burn rate), replay a month of traffic through multi-window burn-rate alerts, and check whether the month triggers SLA credits.

```text
$ python -m slo_budget
allowed downtime   30d      quarter   year
  99.0000%    432.0m   1310.4m   87.6h
  99.5000%    216.0m    655.2m   43.8h
  99.9000%     43.2m    131.0m    8.8h
  99.9500%     21.6m     65.5m    4.4h
  99.9900%      4.3m     13.1m    0.9h

checkout-api SLO 99.9% over 30d: 51.8M requests, SLI 99.9340%, budget used 66% (remaining 34%)

incident   dur   budget   first alert        delay
INC-101    18m   16.5%   fast-burn       3m   storage controller failover stalled writes
INC-102   240m    3.2%   none         -   slow memory leak on API tier caused sporadic 503s
INC-103     6m   13.1%   fast-burn       2m   bad config push to edge load balancers
INC-104    95m   10.3%   fast-burn      23m   degraded cooling forced partial rack shutdown
INC-105     2m    2.9%   fast-burn       2m   brief network partition between AZs

10 alert events (7 pages)
  d04 01:03 -> d04 01:23  page   fast-burn
  d04 01:08 -> d04 01:48  page   medium-burn  (follow-on)
  d04 01:09 -> d04 07:18  ticket slow-burn  (follow-on)
  d16 01:42 -> d16 01:51  page   fast-burn
  d16 01:44 -> d16 02:16  page   medium-burn  (follow-on)
  d16 01:44 -> d16 07:46  ticket slow-burn  (follow-on)
  d22 00:23 -> d22 01:39  page   fast-burn
  d22 01:03 -> d22 02:01  page   medium-burn  (follow-on)
  d22 01:12 -> d22 07:31  ticket slow-burn  (follow-on)
  d28 00:22 -> d28 00:27  page   fast-burn

SLA: availability 99.934% -> credit 0% ($0 on $180,000/month)
```

## Why it matters
A 99.9% SLO allows 43 minutes of full outage a month. Ops teams usually find that out after a 6-minute bad config push has already used 13% of it. Error budgets give engineering and the business one shared number: while there's budget left, ship; when it's burning, freeze risky changes. Burn-rate alerts page on *how fast* the budget is going, not on raw error spikes. That cuts noisy pages and still catches a total outage within about 2 minutes. The replay also shows what the rules miss. INC-102, a 4-hour leak at exactly 6x burn, used 3% of the budget and never paged, because it sat just under the medium-burn threshold. That's the evidence for tuning rules. On a $180k/month contract, the gap between 99.934% (no credit) and a 99.89% month is an $18k credit, so knowing your remaining budget in real time is a revenue issue, not just an engineering one.

## Architecture
```
slo.json (target, traffic profile, SLA tiers)    incidents.csv (start, duration, error rate)
                    │                                         │
                    └──────────► Timeline.synthesize() ◄──────┘
                                 per-minute total/bad + prefix sums (O(1) windows)
                                          │
              ┌───────────────────────────┼─────────────────────────────┐
              ▼                           ▼                             ▼
     BudgetStatus: SLI,          replay(): each minute, for each   incident_cost(): bad
     consumed, remaining         rule fire if long AND short       requests above baseline
              │                  window burn ≥ threshold           as % of budget
              ▼                           │
     sla_credit_pct(tiers)       match_incidents(): detection delay, missed incidents
```
- **Multi-window, multi-burn-rate rules** (14.4x over 1h/5m, 6x over 6h/30m, 1x over 3d/6h) follow the SRE workbook defaults. The long window gives precision, and the short window makes the alert resolve quickly once the problem stops.
- **Synthesized timeline instead of a huge log file.** Incidents plus a diurnal traffic curve fully determine the month, so the sample data is 10 lines and every result is reproducible. Real per-minute counts from Prometheus can be dropped straight into `Timeline(total, bad)`.
- **Prefix sums** make every window query O(1), so replaying 43,200 minutes x 3 rules x 2 windows takes about 0.2s in pure Python.
- **No ML or LLM.** SLO math is arithmetic that people need to trust during an incident review.

## Run
```bash
pip install pytest
python -m pytest -q      # 10 tests
python -m slo_budget     # edit data/slo.json or data/incidents.csv to try other scenarios
```

## Next steps
- Ingest real request/error counters (a Prometheus range query) instead of synthesizing them.
- Add latency SLOs (the share of requests under 300 ms) next to availability.
- Generate the matching Prometheus alerting rules from `DEFAULT_RULES`, so the replayed rules and the deployed rules can't drift apart.
