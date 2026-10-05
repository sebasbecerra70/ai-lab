# Supplier Risk Scoring

A composite risk index for every supplier, built from financial health, country risk and delivery performance. It converts each score into expected annual disruption cost weighted by spend, and stress-tests the portfolio with what-if scenarios (a blockade, a port strike, a supplier in distress).

```text
$ python -m supplier_risk
supplier                       ctry  fin  geo  dlv  risk  tier      P(dis)   exposure
Shenzhen Precision Electronics CN     46   41   62  50.3  high       14.7%  1,846,404  single-source
Taichung Semicon Supply        TW      0   46   35  26.1  medium      3.2%    585,683  single-source
Hanoi Plastics Co              VN     69   42   88  67.5  critical   35.7%    321,108
Busan Battery Cells            KR     22   25   43  30.3  medium      4.2%    196,033
Chennai Firmware Services      IN     30   43   36  36.1  medium      6.1%    147,271  single-source
Guadalajara Logistics          MX     88   34   41  55.4  critical   19.6%    146,851
Bavaria Sensorik GmbH          DE     10   10   21  13.7  low         1.4%     96,629  single-source
Monterrey Metal Works          MX     21   34   25  26.5  medium      3.3%     88,639
Lyon Precision Optics          FR      0   12   12   7.7  low         0.9%     33,836  single-source
Penang Passive Components      MY      0   30   21  16.3  low         1.7%     17,541
Ohio Cable & Harness           US     10   16    8  11.1  low         1.2%     16,840
Ontario Packaging Inc          CA     25   13    5  14.4  low         1.5%      6,607

total expected annual disruption cost $3,503,440; top 3 suppliers = 79%
spend by country: TW 27%, CN 19%, KR 14%, MX 10%  (HHI 0.16)

what-if scenarios
- Taiwan Strait blockade: exposure $3,503,440 -> $6,786,407 (+3,282,967)
    Shenzhen Precision Electronics: high -> critical
    Taichung Semicon Supply: medium -> high
    biggest mover: Taichung Semicon Supply (+2,150,253)
- Trans-Pacific port strike: exposure $3,503,440 -> $5,553,579 (+2,050,139)
    Shenzhen Precision Electronics: high -> critical
    Busan Battery Cells: medium -> high
    biggest mover: Shenzhen Precision Electronics (+1,319,535)
- Supplier distress: exposure $3,503,440 -> $3,670,114 (+166,673)
    biggest mover: Hanoi Plastics Co (+141,823)
```

## Why it matters
Procurement teams usually rank suppliers by spend or by gut feel, and find out about concentration risk during the crisis. Converting risk into **expected dollars** changes the conversation. In the sample, three suppliers carry 79% of the portfolio's disruption exposure, and the top one is a single-source PCB house with mediocre delivery, not the biggest-spend supplier. The Taiwan scenario nearly doubles exposure (+$3.3M) and moves the microcontroller supplier from medium to high. That's the quantified case a supply chain leader needs to fund a second source or a buffer stock: a $400k qualification project against $2M+ of scenario exposure.

## Architecture
```
suppliers.csv (financials, OTD, lead time, ppm, spend, single-source)    countries.csv
        │                                                                      │
        ▼                                                                      ▼
financial_score()  ramp(current ratio, D/E, margin, payables trend)    geo_score()
delivery_score()   ramp(on-time %, lead-time CV, lead time, defects)   political/logistics/hazard
        └───────────────► composite = 0.35 fin + 0.30 geo + 0.35 delivery ◄──────┘
                                     │
                                     ▼
               P(disruption) = logistic(composite)   (calibrated 25→3%, 60→25%)
               exposure $   = P × spend × impact multiplier (×2 if single-source)
                                     │
scenarios.json ──► apply(): country shocks, lead-time multipliers, supplier shocks ──► re-score, diff tiers
```
- **Piecewise-linear "ramps" with explicit good/bad anchors**, instead of statistical normalization. Each anchor is a business statement ("a current ratio under 0.8 is fully risky") that a category manager can argue with and change.
- **Payables stretch is a leading indicator.** Suppliers in distress pay *their* suppliers late before their financials show it, so it gets 20% of the financial score.
- **Expected cost, not just a score.** The probability calibration is illustrative and should be fit to your own disruption history. Even so, the dollar framing makes mitigation spend comparable across suppliers.
- **Scenarios are data** (`scenarios.json`), so risk teams can add one without touching code. `apply()` never mutates the baseline.
- **No LLM needed for the math.** A natural next step is an LLM that reads news and filings and proposes scenario shocks for a human to approve.

## Run
```bash
pip install pytest
python -m pytest -q        # 10 tests
python -m supplier_risk
```

## Next steps
- Calibrate `disruption_probability` with logistic regression on historical disruption events.
- Add sub-tier visibility (a supplier's own key suppliers and their countries).
- Monitor news and credit feeds, and flag suppliers whose inputs moved enough to change tier.
