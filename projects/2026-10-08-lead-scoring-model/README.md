# Explainable Lead Scoring

Scores inbound and outbound B2B leads with a **logistic regression written from scratch**, on firmographic and engagement features. Every score comes with the top reasons behind it, so a rep knows *why* to call.

```text
$ python -m lead_scoring
leads: 300 train / 100 test, base conversion 22.0%
test AUC 0.719   lift@top20% 2.05x

coefficients (standardized, log-odds per 1 sd):
  days_since_last_touch     -0.95
  log_employees             +0.49
  source=partner            +0.41
  demo_requested            +0.37
  industry=logistics        +0.36
  source=inbound            +0.34
  pricing_page_views        +0.25
  source=outbound           -0.22

top 5 open leads to call today:
  L0213 tier A p=0.87  because demo_requested +0.91, source=partner +0.76, industry=logistics +0.70
  L0064 tier A p=0.78  because days_since_last_touch +0.90, log_employees +0.73, email_opens_30d +0.58
  L0277 tier A p=0.73  because demo_requested +0.91, days_since_last_touch +0.81, source=partner +0.76
  L0203 tier A p=0.70  because demo_requested +0.91, industry=logistics +0.70, source=inbound +0.57
  L0282 tier A p=0.69  because demo_requested +0.91, source=partner +0.76, log_employees -0.48

conversion by tier: A: 7/14 (50%)  B: 8/40 (20%)  C: 7/46 (15%)
```

## Why it matters
An SDR team with 400 open leads can make about 60 good calls a day. If they work the list in order of arrival, they spend most of the day on the 78% of leads that won't convert. On the holdout set, the top 20% of leads by score convert at **2x the base rate**, and tier A converts at 50% vs 15% for tier C. Each score shows its reasons ("demo requested, partner-sourced, logistics vertical"), so reps trust it and can open the call with them. A black-box score gets ignored.

## Architecture
```
data/leads.csv ─► raw_features: log10(employees), engagement counts,
                  one-hot industry/source (baseline level dropped)
                          │
                          ▼
                  Standardizer (fit on train only)
                          │
                          ▼
     LogisticRegression: batch gradient descent + L2, stable sigmoid
                          │
             ┌────────────┼──────────────────────┐
             ▼            ▼                      ▼
     holdout AUC /   coefficients       per-lead contributions
     lift@20%        (global drivers)   w_j × z_j → top 3 reasons + tier
```
- **Why logistic regression, not an LLM or gradient boosting?** Sales ops needs calibrated probabilities and drivers it can explain to the CRO. Standardized coefficients answer "what moves conversion" directly, and per-lead contributions add up exactly to the logit (a test checks this). With a few hundred labeled leads, a more flexible model would mostly overfit.
- **Log employees.** Company size matters by order of magnitude: 50 vs 500 employees is a bigger difference than 10,050 vs 10,500.
- **Baseline levels.** One category level per one-hot group is dropped, so the coefficients read as "vs. retail" or "vs. event leads" and aren't collinear with the intercept.
- **The synthetic data has a known ground truth** (`lead_scoring/synth.py`), so the tests can check that the model recovers the right *directions*, not just a good AUC.
- **Recency dominates.** `days_since_last_touch` is the strongest driver: a stale lead goes cold fast. That supports a speed-to-lead SLA.

## Run
```bash
pip install pytest
python -m pytest -q                         # 10 tests
python -m lead_scoring                      # train, evaluate, explain
python -m lead_scoring.synth > data/leads.csv   # regenerate sample data
```

## Next steps
- Calibrate tier cut-offs to rep capacity (e.g. tier A = what the team can call within 24 hours).
- Add time-based validation (train on Q1–Q2, test on Q3) to catch drift.
- Push the score and reasons to a CRM field, and A/B test the routing against round-robin.
