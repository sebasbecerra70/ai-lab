# CRM Pipeline Forecast

A quarterly revenue forecast that learns from your own closed deals. It uses stage conversion rates, a penalty for deals that have stalled, and the odds of a deal closing before the quarter ends, then runs a Monte Carlo simulation to give a range instead of a single number.

```text
$ python -m pipeline_forecast
learned from closed deals:
  stage        win rate   fresh   stale  stale after
  Discovery          7%      9%      5%        22 d
  Qualified         16%     17%     14%        39 d
  Proposal          30%     39%     19%        28 d
  Negotiation       59%     65%     46%        31 d
  Commit            81%     92%     58%        11 d

open pipeline: 64 deals, $4,360k; 45 days left; target $900k
  Discovery    20 deals  $1,126k ->   $17k expected
  Qualified    22 deals  $1,624k ->  $109k expected
  Proposal     11 deals    $642k ->  $125k expected
  Negotiation   7 deals    $504k ->  $250k expected
  Commit        4 deals    $465k ->  $296k expected

forecast:
  rep commit                 $968k
  naive stage-weighted     $1,204k  (ignores aging and timing)
  aged + timed weighted      $797k
  Monte Carlo P10/P50/P90 $507k / $756k / $1,012k
  P(hit $900k)                 24%

commits to pressure-test:
  D052 Riverbend Utilities   $118k jordan  p_close=23%  (stale 61d in Negotiation)
  D063 Meridian Air          $168k jordan  p_close=58%  (stale 21d in Commit)
  D020 Evergreen Foods        $87k avery   p_close=29%  (stale 24d in Commit)
  D030 Brightline Health      $30k avery   p_close=29%  (stale 45d in Commit)
  D015 Granite Telecom        $16k taylor  p_close=23%  (stale 64d in Negotiation)
```

## Why it matters
Reps call $968k in commit against a $900k target, and the textbook stage-weighted pipeline says $1.2M, so the team looks safe. Both numbers ignore two things that sink most quarters: **stalled deals** and **time**. A Commit-stage deal that has sat for 24 days, when winners usually move in 11, wins 58% of the time instead of 92%. And a big Qualified deal can't realistically close in the 45 days left.

Account for both, and the expected number is $797k, with only a **24% chance of hitting plan**. Knowing that in week 7 instead of week 13 is the difference between pulling deals forward, adding pipeline or resetting the board's expectations, and missing quietly. The "pressure-test" list tells a sales manager which five conversations to have this week. It's $420k of called commit that the history says is at risk.

## Architecture
```
data/history.csv (closed deals, one row per stage visited)
      │ fit_stage_stats(): per stage
      │   win rate (Laplace-smoothed), fresh vs stale win rate,
      │   stale threshold = p75 dwell of eventual winners,
      │   days-to-close distribution of winners
      ▼
data/pipeline.csv ──► score_deal(): p_win (fresh/stale) × p_in_quarter (conditional on days already spent)
                             │
                             ├─► stage-weighted sums (naive vs aged+timed)
                             ├─► Monte Carlo: Bernoulli per deal, triangular discount haircut, 10k runs → P10/P50/P90, P(hit)
                             └─► at_risk_commits(): rep "commit" that the model doubts
```
- **Learned, not hard-coded, probabilities.** Most CRMs ship fixed stage weights (Proposal = 50%). Here the weights come from the team's own closed deals, smoothed so a small sample can't produce 0% or 100%.
- **Aging is data-driven.** "Stale" means slower than 75% of deals that went on to win at that stage. The penalty is the observed fresh vs stale win-rate gap, not a guessed decay curve.
- **Timing is conditional.** P(close this quarter) uses the cycle times of winners who had already spent at least as long in the stage. A deal 30 days in isn't treated like one that just arrived.
- **Monte Carlo for the range.** Deal outcomes are lumpy. Two $150k deals swing the quarter, and a single expected value hides that. P10/P90 and P(hit target) are the numbers a CRO actually uses.
- **Trade-offs:** deals are assumed independent (no shared economic shock), and open deals' dwell time is censored (still running) while history is complete, which makes "stale" slightly conservative. Both are easy to explain to a sales leader, and both are listed below.
- **Why no LLM:** this is a counting and probability problem. An LLM adds cost and unpredictability without improving the number. It could later summarize the risk list for a forecast call.

## Run
```bash
python -m pytest -q                         # 10 tests
python -m pipeline_forecast                 # 45 days left, $900k target
python -m pipeline_forecast 20 750000       # late in quarter, lower target
python -m pipeline_forecast.synth           # regenerate the synthetic CRM export
```

## Next steps
- Backtest against previous quarters' snapshots and report forecast error by week of quarter.
- Calibrate per-owner adjustments (some reps sandbag, some are optimists) with shrinkage toward the team rate.
- Add a correlated "macro shock" factor to the simulation so the tails widen realistically.
- Add an LLM-written forecast-call brief from the at-risk list and deal notes.
