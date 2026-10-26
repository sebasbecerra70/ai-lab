# Disk Failure Prediction

Predicts which drives will fail in the next 30 days from SMART-style telemetry, using a logistic regression written from scratch. The alert threshold isn't picked by eye: it's set by the **cost of a surprise failure versus a proactive swap**, and the result is compared with the classic "replace on any reallocated sector" rule.

```text
$ python -m disk_failure
fleet history: 4000 drives, 99 failed within 30 days (2.5%)
test set: 1200 drives, 30 failures   ROC AUC 0.785   avg precision 0.486 (random = 0.025)

coefficients (per 1 sd):
  reallocated_sectors   +0.52
  power_on_hours        +0.38
  temperature_c         +0.32
  pending_sectors       +0.31
  ...
  crc_errors            +0.05

 threshold  flagged  precision  recall       cost
      0.20      123        15%     60%     66,930
      0.40       39        38%     50%     48,090
      0.60       28        50%     47%     47,080
      0.80       17        76%     43%     46,070

costs: unplanned failure $2,400, proactive swap $310
  do nothing (run to failure)       $   72,000
  rule: any realloc/pending sector  $   71,890   flags 139, recall 60%, precision 13%
  model @ cost-optimal t=0.44    $   47,470   flags 37, recall 50%, precision 41%

today's fleet: 17 of 300 drives to swap proactively; top 5:
  D00193 SG-16T  p=0.98  realloc=106 pending= 3 uncorr= 5 seek=0.437
  D00269 HX-12T  p=0.95  realloc= 65 pending=13 uncorr= 0 seek=0.68
  ...
```

## Why it matters
At scale, disk failure is a daily event, not a rare one. A fleet of 40,000 drives at a 2% annualized failure rate loses about two drives every day. A surprise failure costs much more than the drive: an unscheduled tech dispatch, a RAID or erasure-code rebuild that degrades performance for hours, and the risk of a second failure during the rebuild. This project prices that at $2,400 per surprise failure against $310 for a planned swap.

The common rule ("swap anything with reallocated sectors") flags 139 of 1,200 test drives to catch 18 failures. Most of those swaps are wasted, so it saves almost nothing ($71.9k vs $72k for doing nothing). The model flags 37 drives, catches 15, and **cuts expected cost by about a third ($47.5k)**. The cost table also helps the conversation with finance: if the swap cost or rebuild risk changes, rerun with `python -m disk_failure 4000 250` and the right threshold moves with it.

## Architecture
```
disk_failure/synth.py ──► data/fleet_history.csv (4,000 labelled snapshots)  data/fleet_today.csv (300 to score)
                                   │
                                   ▼
features(): log1p(sector/error counts) · hours/10k · temp · seek rate · drive-model one-hot
                                   │ stratified 70/30 split → Scaler (z-score on train only)
                                   ▼
LogisticRegression: full-batch GD, L2, pos_weight=10 for the 2.5% minority, bias initialized at base rate
                                   │
                                   ▼
evaluation: ROC AUC · average precision · precision/recall table
cost: total = FN × unplanned + (TP + FP) × proactive swap → best_threshold() chosen on TRAIN, reported on TEST
baselines: do nothing · SMART rule (realloc > 0 or pending > 0)
```
- **Why logistic regression:** its coefficients are explainable to a hardware team ("reallocated sectors matter most, CRC errors barely matter"). CRC errors are mostly cabling noise, and the model gives them a coefficient of about zero. It trains in a second on the standard library, and with 9 features gradient boosting would gain little and cost interpretability.
- **Imbalance handled with weights, not resampling.** `pos_weight` makes each failure count 10×. Probabilities are then "inflated", which is fine because the threshold is chosen on cost, not at 0.5.
- **Average precision, not just AUC.** With a 2.5% base rate, AUC flatters every model. Average precision (0.49 vs 0.025 random) reflects what the on-call tech actually experiences: how many flagged drives are real.
- **No test-set peeking.** The cost-optimal threshold is chosen on training predictions and reported on held-out drives, so the headline saving is an honest estimate.
- **Trade-off:** one snapshot per drive ignores trends. In real SMART data the *rate of change* of reallocated sectors is often the strongest signal. That's the first next step.

## Run
```bash
python -m pytest -q                 # 9 tests
python -m disk_failure              # default costs $2,400 / $310
python -m disk_failure 4000 250     # higher rebuild risk, cheaper drives
python -m disk_failure.synth        # regenerate the synthetic fleet
```

## Next steps
- Add time-series features: 7- and 30-day deltas of reallocated and pending sectors.
- Calibrate probabilities (Platt or isotonic) so p=0.4 means 40%, which helps capacity planning for spares.
- Train on the public Backblaze SMART dataset and compare feature importances.
- Feed flagged drives into the change-risk scorer so swaps are batched into low-risk maintenance windows.
