# Partner Fit Scorer

Rank a pipeline of potential partners (ISVs, SIs, resellers, marketplaces) on one defensible fit score. Criteria weights come from AHP pairwise judgments, and a sensitivity check shows whether the #1 pick survives disagreements about those weights.

```text
$ python -m partner_fit
AHP weights (from 15 pairwise judgments)
  strategic_alignment   28.8%  #################
  revenue_potential     28.8%  #################
  customer_overlap      17.0%  ##########
  channel_conflict       9.8%  ######
  integration_effort     9.8%  ######
  financial_health       5.9%  ####
  consistency ratio 0.007 (OK, threshold 0.10)

rank partner                        type          fit  why
1    Atlas ERP                      ISV          72.1  strongest on revenue_potential, financial_health; weakest on integration_effort
2    Northwind Logistics Cloud      ISV          68.3  strongest on strategic_alignment, channel_conflict; weakest on revenue_potential
3    Pioneer Robotics               OEM          57.5  strongest on strategic_alignment, channel_conflict; weakest on customer_overlap
4    Cobalt Freight Marketplace     Marketplace  56.6  strongest on customer_overlap, integration_effort; weakest on revenue_potential
5    Brightline Systems Integrator  SI           54.6  strongest on integration_effort, revenue_potential; weakest on customer_overlap
6    Harbor Payments                ISV          49.2  strongest on financial_health, integration_effort; weakest on revenue_potential
7    Summit Reseller Group          Reseller     41.2  strongest on integration_effort, revenue_potential; weakest on financial_health
8    Meridian Consulting            SI           36.8  strongest on integration_effort, financial_health; weakest on customer_overlap

robustness: Atlas ERP stays #1 in 21/24 single-weight shifts (±25%, ±50%)
  revenue_potential -50% -> Northwind Logistics Cloud leads
  revenue_potential -25% -> Northwind Logistics Cloud leads
  strategic_alignment +50% -> Northwind Logistics Cloud leads
```

## Why it matters
A BD team typically has 20-40 inbound and outbound partner candidates and capacity to properly launch 3-4 a year. Each launch costs 3-6 months of a partner manager's time plus engineering for the integration. The usual way to decide is "loudest exec wins". AHP makes the team agree on *what matters* first ("is revenue 3x more important than integration effort?"). It then checks those judgments for internal consistency, and scores every partner the same way. The sensitivity table is what you bring to the exec review. In the sample, Atlas ERP leads in 21 of 24 weight shifts, and it only loses the top spot to Northwind if leadership decides near-term revenue matters much less than the matrix says. That makes the decision a short, focused conversation instead of an open-ended debate.

## Architecture
```
criteria.json (direction + 15 pairwise judgments)        partners.csv (raw attributes)
        │                                                       │
        ▼                                                       ▼
pairwise_matrix() → power-iteration eigenvector          normalize(): min-max 0..1,
        │            → λmax, CI, CR (Saaty RI)              cost criteria inverted
        ▼                                                       │
     weights ───────────────────────────► score(): Σ weight × normalized × 100
                                                    │
                          ┌─────────────────────────┼──────────────────────┐
                          ▼                         ▼                      ▼
                     ranked table             explain(): strongest   sensitivity(): ±25/50%
                                              and weakest criteria   per weight → leader flips
```
- **AHP over hand-picked weights.** People are better at comparing two things than at assigning percentages. The consistency ratio (CR < 0.10) catches circular judgments before they distort the ranking.
- **Min-max normalization** keeps scores readable (0-100) and treats cost criteria (integration effort, channel conflict) correctly. The trade-off: scores are relative to the current pipeline, so adding a new partner can shift everyone's score.
- **Additive contributions** let the explanation show *why* a partner ranks where it does, which is what partner managers need to take back to the candidate.
- **No LLM.** Weighting criteria is a judgment call and scoring is arithmetic. Both need to be transparent and reproducible, and an LLM narrative wouldn't make the decision any more defensible.

## Run
```bash
pip install pytest
python -m pytest -q        # 10 tests
python -m partner_fit      # edit data/criteria.json or data/partners.csv and rerun
```

## Next steps
- Collect pairwise judgments from several stakeholders, and combine them with the geometric mean (the standard group-AHP approach).
- Add a "must-have" gate (e.g., SOC 2, minimum financial health) before scoring.
- Track partner outcomes after launch, to check how well the fit score predicted results.
