# Shipment Delay Risk

Scores every planned shipment's **probability of arriving late** with a boosted ensemble of decision stumps, explains each score in plain terms, rolls it up into a lane × carrier risk matrix, and suggests a carrier swap when another carrier is materially safer.

```text
$ python -m delay_risk
Trained 40 stumps on 360 shipments (weeks 0-37), tested on the next 120; delay rate 44%
model                        AUC   Brier   prec@top24
carrier on-time history     0.59   0.255          58%
stump ensemble              0.73   0.214          79%
Top drivers: weather_index 25%, carrier_otp_90d 20%, ship_dow 18%, schedule_slack 13%, mode 10%

Lane x carrier risk, typical FTL load (Tue, off-peak, median weather)
lane       Bluewater   Crestway  Northpass    Redline   best
ATL-CHI          13%        28%        12%        10%   Redline
CHI-TOR          27%        49%        25%        22%   Redline
DAL-LAX          14%        31%        13%        12%   Redline
LAR-MTY          22%        42%        20%        18%   Redline
LAX-PHX          13%        28%        12%        10%   Redline
MEM-NYC          14%        31%        13%        12%   Redline
SAV-ATL           6%        15%         6%         5%   Redline
SEA-SLC          13%        28%        12%        10%   Redline

Next week's plan: 14 shipments
  P0001 LAR-MTY  Crestway    86% HIGH  carrier_otp_90d <= 0.865; mode=LTL  -> Redline 54%
  P0004 SEA-SLC  Northpass   70% HIGH  ship_dow=Fri; mode=LTL  -> Redline 50%
  P0013 MEM-NYC  Redline     62% HIGH  weather_index > 0.635; ship_dow=Fri
  P0009 SAV-ATL  Northpass   55% HIGH  weather_index > 0.635; carrier_otp_90d <= 0.865  -> Redline 33%
  P0007 LAR-MTY  Crestway    50% HIGH  carrier_otp_90d <= 0.865; mode=LTL  -> Redline 23%
  P0012 MEM-NYC  Bluewater   48% watch mode=LTL; ship_dow=Thu (not Wed)  -> Redline 38%
  P0005 MEM-NYC  Redline     37% watch weather_index > 0.635; schedule_slack <= 3.417
  P0002 LAR-MTY  Redline     34% watch mode=LTL; cross_border=yes
  P0003 LAX-PHX  Bluewater   31% watch weather_index > 0.635; schedule_slack <= 3.417
  P0010 SEA-SLC  Bluewater   31% watch weather_index > 0.635; schedule_slack <= 3.417
  P0000 MEM-NYC  Redline     29% ok
  P0008 LAR-MTY  Crestway    25% ok
  P0006 LAX-PHX  Bluewater   15% ok
  P0011 SAV-ATL  Bluewater   14% ok
```

## Why it matters
A late inbound load costs far more than the freight bill: a missed dock appointment, overtime for the receiving crew, and sometimes a line stop or a retailer chargeback of 3–5% of invoice value. Most transportation teams triage with one number per carrier (90-day on-time %). On the holdout weeks that baseline ranks risk barely better than a coin flip (AUC 0.59). The stump ensemble reaches **AUC 0.73**, and **79% of its 24 riskiest shipments were actually late, against 58%** for the carrier baseline. A planner with time to expedite, re-tender or pre-alert a customer on only one load in five gets about a third more true hits from the same effort.

The output is meant for the Monday planning meeting. P0001 (Crestway LTL to Monterrey) is 86% likely to be late, mainly because of the carrier's recent on-time record and LTL consolidation; re-tendering it to Redline cuts the risk to 54%. P0013 is high risk on Redline too, but the drivers are weather and a Friday pickup, so the fix is to move the pickup day rather than the carrier.

## Architecture
```
data/shipments.csv ─► featurize: + schedule_slack (planned days × 700 km / distance)
 (480 loads, 52 wks)           + cross_border flag
        │
        ▼
 time_split: train on weeks 0-37, test on the newest 25%
        │
        ▼
 StumpEnsemble.fit (AdaBoost, 40 rounds)
   candidate splits: numeric "x <= t" (≤12 thresholds), categorical "x == v"
   each round: pick the stump with the lowest weighted error, alpha = ½ ln((1-ε)/ε), reweight
        │
        ├─► predict_proba = σ(2 · Σ alpha·vote)   reasons = top features pushing toward "late"
        ├─► holdout: AUC, Brier, precision@top-20% vs the carrier-history baseline
        ├─► lane_carrier_matrix: typical FTL load under median conditions, per lane × carrier
        └─► score_plan(data/upcoming.csv): tier, reasons, carrier swap if ≥10 pts safer
```
- **Why stumps and not a deep tree or an LLM?** Each stump is a one-line rule a transportation manager can check ("Friday pickup", "carrier OTP ≤ 86.5%"). Boosting many of them captures additive effects without a black box. With 480 labelled loads, a deeper model would mostly fit noise, and an LLM adds nothing to tabular scoring.
- **Margin → probability.** AdaBoost's score estimates half the log-odds, so σ(2F) gives usable probabilities without a separate calibration step. The Brier score checks that on the holdout.
- **Time-based split.** The model is tested only on weeks it never saw, the way it will be used. A random split would leak seasonal weather into training.
- **The matrix holds conditions fixed.** A carrier's raw delay rate mixes its own performance with the lanes, seasons and days it was given. Scoring the same typical load for every carrier isolates the carrier effect, which is the number to bring to a carrier award or QBR.
- **Reasons come from the model itself.** Each feature's signed contribution is the sum of its stumps' votes, so the explanation is exact rather than a post-hoc approximation.
- Standard library only. Training takes about 0.1 s.

## Run
```bash
pip install pytest
python -m pytest -q          # 9 tests
python -m delay_risk         # 40 boosting rounds
python -m delay_risk 80      # more rounds
```
Replace `data/shipments.csv` with your TMS export (same columns, `delayed` = 1 if delivered after the appointment) and `data/upcoming.csv` with next week's tendered loads.

## Next steps
- Predict delay hours (regression stumps) as well as late/on-time, so a 2-hour slip and a 2-day slip are treated differently.
- Pull live weather and border-wait feeds to fill in `weather_index` and a crossing-delay feature on the day of the move.
- Weight the swap suggestion by rate difference, so a planner sees the cost per point of risk removed.
