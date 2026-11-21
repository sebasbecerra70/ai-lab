# OKR Reporter

Score every key result from live metrics, compare progress with where it should be at this point in the quarter, forecast quarter-end from the recent trend, and have an LLM draft the weekly status update. The draft is then fact-checked against the numbers.

```text
$ python -m okr_reporter
Q4 OKRs, week 8 of 13 (62% of the quarter elapsed)

KR     key result                                       now        target  done  pace       forecast  status
O1  Make self-serve onboarding effortless  (score 57%, projected 89%)
KR1.1  Activation rate (7-day)                        35.7%         40.0%   52%   62%          38.9%  at risk
KR1.2  Median time-to-first-value                    22 min        15 min   74%   62%        8.5 min  on track
KR1.3  Onboarding support tickets per week               92            60   47%   62%             73  at risk
O2  Grow expansion revenue from teams  (score 33%, projected 55%)
KR2.1  Net revenue retention                         105.0%        112.0%   12%   62%         105.5%  off track
KR2.2  Workspaces on Team plan                          979         1,100   57%   62%          1,086  on track
KR2.3  Seat-based upgrade flow shipped         2 milestones  4 milestones   50%   62% 3.5 milestones  at risk
O3  Earn enterprise trust  (score 60%, projected 98%)
KR3.1  p95 API latency                               431 ms        300 ms   61%   62%         158 ms  on track
KR3.2  SOC 2 Type II controls evidenced                  47            64   60%   62%             62  on track

--- status update draft ---
**Headline:** 4 of 8 KRs on track or done, 4 need attention.

**Going well**
- KR1.2 Median time-to-first-value: 22 min against a 15 min target, 74% of the way there (on track).
- KR2.2 Workspaces on Team plan: 979 against a 1,100 target, 57% of the way there (on track).
- KR3.1 p95 API latency: 431 ms against a 300 ms target, 61% of the way there (on track).
- KR3.2 SOC 2 Type II controls evidenced: 47 against a 64 target, 60% of the way there (on track).

**Needs attention**
- KR2.1 Net revenue retention is off track: 12% done vs 62% expected; the current trend lands at 105.5% against 112.0%.
- KR1.1 Activation rate (7-day) is at risk: 52% done vs 62% expected; the current trend lands at 38.9% against 40.0%.
- KR1.3 Onboarding support tickets per week is at risk: 47% done vs 62% expected; the current trend lands at 73 against 60.
- KR2.3 Seat-based upgrade flow shipped is at risk: 50% done vs 62% expected; the current trend lands at 3.5 milestones against 4 milestones.

**Ask:** agree on a recovery plan or a re-scoped target for KR2.1 by next review.
---
fact check: passed
```

## Why it matters
In most product orgs, the weekly OKR update is a PM copying numbers from three dashboards into a doc and then writing "on track" by feel. That takes 1-2 hours per PM per week, and the "by feel" part is the problem. In the sample, net revenue retention looks fine at 105% until you see it is 12% of the way to target with 62% of the quarter gone, and the trend lands at 105.5% against 112%. This tool replaces "feels on track" with a pace-adjusted status and a forecast. It then names the KR to escalate (KR2.1, the highest-weight KR furthest from target), so the leadership meeting starts with the decision instead of the readout.

## Architecture
```
okrs.json (baseline, target, weight)   metrics.csv (weekly values)
            └──────────────┬───────────────┘
                           ▼
   progress(): (now − baseline) / (target − baseline), direction-aware, clamped ≥ 0
   expected  = week / weeks_in_quarter (linear plan)
   forecast  = now + LS slope(last 4 weeks) × weeks left → projected progress
   status    = done | on track (≥90% projected) | at risk (≥70%) | off track
   objective = weighted mean, capped at 100% per KR; biggest_gap = max weight × (1 − projected)
                           ▼
   facts(): one pipe-delimited line per KR + OVERALL + BIGGEST GAP
                           ▼
   LLMClient (Mock | Claude): "use only these facts", under 200 words
                           ▼
   check(): every number in the draft must appear in the facts; every lagging KR must be mentioned
```
- **Code does the math, the LLM does the prose.** Status, forecast and the escalation pick are deterministic and testable. The model only turns them into readable text.
- **Pace beats percent-complete.** 57% done in week 8 of 13 is fine; 12% done is not. Status comes from projected attainment, so a KR with a strong recent trend isn't flagged just because it started slowly.
- **Trend over the last 4 weeks, least squares.** That reacts to recent changes without being thrown by one noisy week. The trade-off shows on p95 latency: a cache rollout in week 6 is a step change, and the linear trend overshoots to a 158 ms forecast. That doesn't affect the status, since projected progress is capped at 100%, but the forecast value should be read with that in mind.
- **The fact check is the trust layer.** A status update with one invented number gets the whole report ignored. Unknown numbers or skipped at-risk KRs are surfaced before anything is sent.

## Run
```bash
pip install pytest
python -m pytest -q                                   # 9 tests
python -m okr_reporter                                # mock LLM, offline
python -m okr_reporter my_okrs.json my_metrics.csv
ANTHROPIC_API_KEY=... python -m okr_reporter          # Claude writes the draft, same fact check
```

## Next steps
- Detect step changes (changepoints) and forecast from the post-change level instead of a blended slope.
- Pull metrics directly from the warehouse or product analytics API instead of a CSV export.
- Keep week-over-week history so the update can say "moved from at risk to on track".
