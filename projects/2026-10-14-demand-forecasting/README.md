# Demand Forecasting Baselines

Four classic forecasting baselines (naive / seasonal naive, moving average, **Holt-Winters** and **Croston-SBA**) written from scratch and compared per SKU with a **rolling-origin backtest** on WAPE, MAPE and bias. Intermittent SKUs are detected and judged on the right metric.

```text
$ python -m demand_forecast
Rolling-origin backtest: 20 origins x 4-week horizon (last 80 weeks)

SKU-STRETCH-WRAP  (208 weeks, mean 399.6/wk, ADI 1.00 -> smooth, ranked by weekly WAPE)
    model              WAPE    MAPE    bias  WAPE-4wk
    holt_winters       7.4%    7.9%   +0.3%      3.7%  <- best
    seasonal_naive     8.4%    9.1%   +0.7%      3.4%
    naive             11.2%   11.8%   +0.8%     10.0%
    moving_avg_8      18.8%   20.6%   +6.1%     18.7%
    croston_sba       23.5%   26.0%   +0.9%     23.0%

SKU-LABEL-4X6  (208 weeks, mean 448.4/wk, ADI 1.00 -> smooth, ranked by weekly WAPE)
    model              WAPE    MAPE    bias  WAPE-4wk
    moving_avg_8       3.1%    3.1%   -2.3%      2.8%  <- best
    naive              3.8%    3.8%   -0.7%      3.4%
    holt_winters       5.0%    5.2%   +0.9%      4.8%
    croston_sba        9.2%    9.1%   -9.2%      9.2%
    seasonal_naive    19.8%   19.9%  -19.8%     19.8%

SKU-GLOVES-L  (208 weeks, mean 149.2/wk, ADI 1.00 -> smooth, ranked by weekly WAPE)
    model              WAPE    MAPE    bias  WAPE-4wk
    moving_avg_8       5.9%    6.0%   +0.4%      4.1%  <- best
    holt_winters       7.2%    7.4%   +0.7%      4.3%
    croston_sba        7.3%    7.2%   -4.6%      5.0%
    seasonal_naive     8.2%    8.4%   +1.7%      4.7%
    naive              8.2%    8.2%   -1.8%      6.6%

SKU-SPARE-MOTOR  (208 weeks, mean 0.6/wk, ADI 4.06 -> intermittent, ranked by WAPE-4wk)
    model              WAPE    MAPE    bias  WAPE-4wk
    croston_sba      139.3%   66.2%   -5.9%     79.5%  <- best
    moving_avg_8     146.9%   68.3%   -1.8%     92.9%
    holt_winters     160.8%   76.9%   +2.3%     94.8%
    seasonal_naive   176.8%   97.9%   -1.8%    126.8%
    naive            189.3%  103.1%  +21.4%    178.6%
```

## Why it matters
Forecast error turns directly into working capital: over-forecast and cash sits on the shelf, under-forecast and you stock out. For a distributor with $20M of inventory, a few points of WAPE is a seven-figure safety-stock decision. Before buying an ML forecasting platform, a planning team should know **what the simple baselines already achieve per SKU type**. Here Holt-Winters wins on the seasonal SKU, an 8-week moving average is hard to beat on stable demand, and Croston wins on the spare part. The spare-part rows also show that **MAPE is misleading for intermittent demand** (zeros are dropped, so it looks better than it is), and that weekly WAPE punishes every model for missing which week a single unit is ordered. Ranking intermittent SKUs on 4-week totals (lead-time demand) matches how the reorder decision is actually made.

## Architecture
```
data/weekly_demand.csv (4 SKU archetypes x 208 weeks, from synth.py)
          │
          ▼
   ADI (average demand interval) ── > 1.32 → intermittent
          │
          ▼
   rolling-origin backtest: 20 origins × 4-week horizon
   each model sees only history[:origin]
          │
   ┌──────┼─────────────┬───────────────┬─────────────────┐
 naive  seasonal_naive  moving_avg_8   holt_winters      croston_sba
                                       (additive, grid-  (size & interval
                                        searched α,β,γ)   smoothed, SBA bias fix)
          │
          ▼
   WAPE · MAPE · bias · WAPE on 4-week totals  →  best model per SKU
```
- **Baselines first.** Any ML model has to beat these on the same backtest to justify itself. Often the moving average is the honest answer.
- **Rolling origins** (20 cut points) average out lucky weeks. A single holdout split routinely picks the wrong model.
- **WAPE over MAPE.** WAPE is volume-weighted and defined when actuals are zero. Bias is reported separately because over- and under-forecasting cost different amounts.
- **Holt-Winters parameters** are chosen by a small grid on in-sample one-step error. That's robust and fast, and avoids a full optimizer.
- **Croston with the Syntetos-Boylan correction**, because plain Croston is biased upward on intermittent series.

## Run
```bash
pip install pytest
python -m pytest -q                                     # 9 tests
python -m demand_forecast                               # backtest all SKUs
python -m demand_forecast.synth > data/weekly_demand.csv   # regenerate data
```

## Next steps
- Add prediction intervals from backtest residuals and feed them into safety stock (project 020).
- Classify SKUs on ADI × CV² (smooth / erratic / intermittent / lumpy) and route models automatically.
- Add a gradient-boosted model with calendar and promo features, and require it to beat the baselines per SKU class.
