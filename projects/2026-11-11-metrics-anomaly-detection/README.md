# Product Metrics Anomaly Detection

Flag the KPI days that are actually abnormal (not just Sundays) using robust seasonal decomposition and modified z-scores. Downstream moves are suppressed when an upstream metric already explains them.

```text
$ python -m kpi_anomaly
120 days x 4 KPIs, 9 labeled anomalies (incl. downstream)

weekly seasonality (dau): Mon 1.01  Tue 1.03  Wed 1.03  Thu 1.02  Fri 0.97  Sat 0.74  Sun 0.70

anomalies (|robust z| >= 3.5)
  day  24 Wed  dau              -19.3% vs expected  z=  -8.6
  day  24 Wed  revenue          -18.8% vs expected  z=  -3.8  <- explained by dau
  day  42 Sun  signups          +57.5% vs expected  z= +12.7
  day  53 Thu  conversion_rate  +10.0% vs expected  z=  +3.7
  day  53 Thu  revenue          +19.7% vs expected  z=  +4.0  <- explained by conversion_rate
  day  59 Wed  conversion_rate  -33.8% vs expected  z= -12.4
  day  59 Wed  revenue          -33.4% vs expected  z=  -6.7  <- explained by conversion_rate
  day  78 Mon  revenue          -27.0% vs expected  z=  -5.4
  day  79 Tue  revenue          -19.2% vs expected  z=  -3.9
  day  97 Sat  dau              +16.5% vs expected  z=  +7.4
  day 105 Sun  signups          -42.5% vs expected  z=  -9.4
  day 109 Thu  signups          +16.5% vs expected  z=  +3.6

method                       precision  recall
decomposition + robust z           75%    100%
naive z-score on raw values       100%     22%

12 flags -> 9 root-cause alerts after suppressing explained downstream moves
```

## Why it matters
Every product org has a KPI dashboard, and almost nobody looks at it closely enough to catch a broken tracking pixel or a checkout bug within a day. Naive "3 standard deviations" alerts get muted within a week, because they fire on every weekend dip and miss real drops that land inside the normal range. In the sample, the naive method catches only 2 of 9 real anomalies. The decomposition approach catches all 9 with 75% precision. It also collapses 12 flags into 9 root-cause alerts, so the on-call PM sees "conversion -34%" instead of three separate pages for conversion, revenue and AOV. A checkout bug caught on day 1 instead of at the weekly business review saves about six days of lost conversion. At $50k/day revenue and a 34% drop, that's roughly $100k.

## Architecture
```
kpis.csv (day, weekday, dau, signups, conversion_rate, revenue, labels)
        │ per metric
        ▼
decompose():  trend    = centered rolling MEDIAN (15 days)
              seasonal = median ratio per weekday, normalized to mean 1
              residual = value / (trend × seasonal) − 1
        │
        ▼
robust_z(residual) = 0.6745 (r − median) / MAD     flag |z| ≥ 3.5
        │
        ▼
explain: revenue flag + same-day dau/conversion flag → "explained by", suppressed as a root alert
        │
        ▼
score() vs labeled anomalies ◄── naive z-score on raw values (baseline)
```
- **Medians everywhere.** A rolling mean and a classic z-score are both pulled toward the anomaly they're supposed to detect. Medians and MAD ignore up to half the points being bad, so one outage doesn't hide itself.
- **Multiplicative decomposition** fits product metrics, where weekends are a percentage dip rather than a fixed amount, and it keeps working as the metric grows.
- **A metric dependency map** (`revenue ~ dau x conversion`) is a small piece of domain knowledge that cuts alert volume a lot. It's the cheapest form of root-cause analysis.
- **Why not an LLM or deep model?** 120 points per metric is far too little to train on, and the method has to be explainable in one sentence to a PM ("19% below what a typical Wednesday at this trend would be").

## Run
```bash
pip install pytest
python -m pytest -q                      # 10 tests
python -m kpi_anomaly --threshold 3.5    # raise to 4.5 for fewer, higher-confidence alerts
```

## Next steps
- Add holiday and launch calendars as known events, so they aren't flagged.
- Track threshold precision and recall over time with analyst feedback ("real / not real") on each alert.
- Use the LLM layer only for the alert text: summarize the flagged metric, its drivers, and recent deploys.
