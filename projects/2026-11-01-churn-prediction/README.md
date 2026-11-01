# Churn Prediction

Builds the **cohort retention triangle** with a Kaplan-Meier blended curve, trains a from-scratch **logistic regression** that predicts six-month churn from an account's first 30 days, ranks the drivers, and lists which young accounts customer success should call this week.

```text
$ python -m churn
Cohort retention (997 accounts; % still active after month N; C01 = oldest signup month)
cohort  size    M1   M2   M3   M4   M5   M6   M7   M8   M9  M10  M11  M12
C01      61   89%  87%  82%  80%  79%  79%  77%  77%  75%  75%  75%  74%
C02      78   81%  74%  67%  62%  58%  58%  56%  56%  54%  53%  53%
C03      71   93%  85%  82%  76%  69%  69%  69%  69%  68%  66%
C04      83   93%  86%  81%  77%  75%  71%  70%  70%  66%
C05      77   94%  88%  81%  75%  73%  70%  65%  65%
C06      92   92%  87%  80%  79%  76%  74%  73%
C07      80   92%  82%  78%  76%  72%  68%
C08      92   93%  85%  83%  80%  76%
C09      88   91%  81%  73%  65%
C10      85   89%  80%  76%
C11      92   86%  80%
C12      98   85%
blended        90%  83%  77%  74%  70%  68%  66%  66%  64%  63%  63%  62%   (Kaplan-Meier)

Early-warning model: P(cancel within 6 months | first 30 days), trained on 379 accounts, tested on 163 (churn rate 27%)
  holdout AUC 0.90  vs  0.78 for 'fewest active days' alone
  drivers (odds ratio per +1 std dev; <1 protects, >1 raises churn):
    billing=annual               0.30
    active_days_first30          0.45
    integrations_first30         0.49
    plan=business                0.61
    plan=team                    0.74

At-risk: 349 active accounts still inside their first 6 months; top 8
  A0957 C12 starter     4 seats   90%  active days 3; billing monthly
  A0806 C10 starter     4 seats   90%  active days 2; billing monthly
  A0962 C12 starter     5 seats   90%  active days 1; billing monthly
  A0959 C12 starter     2 seats   90%  active days 1; billing monthly
  A0703 C09 starter     4 seats   86%  active days 6; billing monthly
  A0981 C12 starter     2 seats   86%  active days 5; billing monthly
  A0872 C11 starter     3 seats   84%  active days 6; billing monthly
  A0568 C08 starter     3 seats   84%  active days 5; billing monthly

What-if: 119 young accounts never finished onboarding. If they had, modelled 6-month churn
falls 8.1 pts each (~10 accounts kept). Correlational: confirm with an onboarding-outreach A/B test.
```

## Why it matters
For a SaaS product, the blended curve says a third of new accounts are gone within six months, and most of that loss happens in months 1–3. By month 6 the cohort is already lost, so the useful signal is in the **first 30 days**. Using only first-month behaviour, the model separates future churners well (holdout **AUC 0.90**, against 0.78 for the "low activity" rule most teams start with). The drivers turn that into product work:

- **Annual billing** cuts the odds of churn by 70% per standard deviation. That points to a pricing and packaging lever (annual discounts at the end of the trial), not only a CS one.
- **Active days and integrations connected** are the activation metrics to put on the onboarding dashboard. An account that connects a second integration is much harder to replace.
- The at-risk list gives a CSM team a short list of starter accounts with 1–6 active days on monthly billing: 8 calls, not 349.

The onboarding what-if is labelled correlational on purpose. It sizes the opportunity (about 10 of the 119 young accounts without onboarding) to justify an outreach experiment, and it is not evidence that the outreach works.

## Architecture
```
data/accounts.csv (997 accounts, 12 monthly cohorts, first-30-day signals, churn month)
        │
        ├─► retention_triangle: % active after month N, only for months each cohort has lived
        ├─► blended_curve: Kaplan-Meier, Π (1 − churned_m / at_risk_m) across all cohorts
        │
        └─► mature accounts (≥ 6 months observed) ─► split 70/30 (seeded)
                    │
                    ▼
            raw_features: 5 numeric + one-hot plan/billing (baselines: starter, monthly)
            standardize ─► ChurnModel: full-batch gradient descent, L2, bias starts at base-rate log-odds
                    │
                    ├─► holdout AUC (rank-based, tie-aware) vs single-signal baseline
                    ├─► drivers: exp(coef) = odds ratio per +1 std dev
                    └─► young active accounts ─► P(churn) + reasons (largest positive coef × z-score)
                                              └─► counterfactual: set onboarding_completed = 1
```
- **Logistic regression, not a black box.** A PM needs to say "annual billing and integrations are what keep accounts" in a roadmap review. Standardized coefficients give odds ratios that can be compared directly, and per-account reasons are exact contributions rather than an approximation layer.
- **Only mature accounts train the model.** An account with 2 months of history that hasn't churned yet is not a negative label. Training on it would bias the model toward "everyone stays". Those accounts are what the model scores instead.
- **Kaplan-Meier for the blended curve.** Averaging the triangle's columns overweights the few old cohorts in the tail and can produce a curve that goes back up. KM uses every cohort for every month it has observed.
- **Correlated features are expected.** Onboarding, active days and integrations move together, so individual coefficients share credit. That is why `seats` and onboarding rank below the top five even though the plan-level story is clear. A tree model would hide this rather than fix it.
- **Why not an LLM?** This is tabular prediction with a few hundred labels. An LLM could draft the CSM outreach email for each at-risk account later, but the scoring should stay cheap, deterministic and auditable.
- Standard library only.

## Run
```bash
pip install pytest
python -m pytest -q        # 8 tests
python -m churn            # top 8 at-risk accounts
python -m churn 20         # top 20
```
Replace `data/accounts.csv` with a warehouse export (one row per account: signup cohort, first-30-day usage, churn month or blank).

## Next steps
- Score accounts weekly on rolling 30-day usage (not only the first month) to catch later-tenure churn before renewal.
- Add a survival model (discrete-time hazard) so the output is *when* an account is likely to churn, not just whether.
- Close the loop: log CSM outreach per account and measure uplift against a holdout group.
