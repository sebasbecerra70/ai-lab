# RICE Prioritizer

Scores a backlog with **RICE** (Reach × Impact × Confidence ÷ Effort) and **stress-tests the ranking** with Monte Carlo and one-at-a-time sensitivity. It then packs a capacity- and dependency-aware quarterly roadmap and has an LLM write the exec-facing rationale.

```text
$ npm run demo
RICE ranking (top 4 odds from 2000 Monte Carlo runs; reach ±30%, effort ±40%, widened by 1/confidence)
rank  feature                   RICE   P(top4)  rank p10-p90  verdict       most sensitive to
   1  Scheduled CSV export      2100     100%           1-3  robust in     reach (±1 ranks)
   2  Slack/Teams alerts        1600      91%           1-4  robust in     reach (±1 ranks)
   3  Dark mode                 1250      80%           2-5  robust in     reach (±2 ranks)
   4  SAML SSO + SCIM            960      49%           2-6  contested     reach (±2 ranks)
   5  Webhooks + retries         960      49%           2-6  contested     effort (±2 ranks)
   6  Admin audit log            733      17%           4-7  robust out    effort (±2 ranks)
   7  Demand forecast widget     375      10%           4-8  robust out    reach (±1 ranks)
   8  Mobile offline mode        270       4%           6-8  robust out    effort (±1 ranks)

Roadmap: 2 quarters × 6 person-months
  Q1 (5.5/6 pm): Scheduled CSV export, Slack/Teams alerts, Dark mode, Webhooks + retries
  Q2 (4.5/6 pm): SAML SSO + SCIM, Admin audit log
  not scheduled: Demand forecast widget (no capacity left)
  not scheduled: Mobile offline mode (no capacity left)

Rationale:
- Q1 Scheduled CSV export: RICE 2100 (#1); Top support ticket theme. Risk: ranking holds under estimate uncertainty.
- Q1 Slack/Teams alerts: RICE 1600 (#2); Asked by ops managers. Risk: ranking holds under estimate uncertainty.
- Q1 Dark mode: RICE 1250 (#3); Low effort, low impact. Risk: ranking holds under estimate uncertainty.
- Q1 Webhooks + retries: RICE 960 (#5); Unblocks ERP integrations. Risk: ranking is sensitive to estimates (top-N in 49% of simulations), so validate reach/effort first.
- Q2 SAML SSO + SCIM: RICE 960 (#4); Blocker in 6 enterprise deals. Risk: ranking is sensitive to estimates (top-N in 49% of simulations), so validate reach/effort first.
- Q2 Admin audit log: RICE 733 (#6); SOC 2 finding. Risk: low odds of being a top item; keep scope small.
```

## Why it matters
A RICE spreadsheet gives false precision: "SSO 960 vs webhooks 960" looks like a tie broken by a coin flip, and in practice by whoever argues loudest. The Monte Carlo shows the top 3 are **robust** (rank stays in the top 4 in ≥80% of plausible estimate worlds), while SSO and webhooks are **contested at 49%**. That tells the PM where an hour of discovery (better reach and effort estimates) is worth more than another prioritization meeting. The roadmap step shows why rank #5 can ship before #4: SSO's 3 person-months don't fit in what's left of Q1.

## Architecture
```
data/features.json ─► validate (impact scale, confidence ∈ (0,1], deps exist)
                              │
                              ▼
                       rank(): RICE score
                 ┌────────────┼──────────────────────────┐
                 ▼            ▼                          ▼
        oneAtATime ±30%   monteCarlo (seeded,       planRoadmap
        → most sensitive  2000 runs, reach ±30%,    greedy by RICE into
          input per item  effort ±40%, × 1/conf)    quarter capacity,
                          → P(top N), p10–p90 rank  deps respected
                              │                          │
                              └──────────┬───────────────┘
                                         ▼
                      LLMClient (TemplateLLM | Claude) → rationale
```
- **Uncertainty scales with confidence.** A 50%-confidence item gets twice the estimate spread. That uses the C in RICE as a real input to the simulation, not just a multiplier that people game.
- **Simulation, not optimization.** The useful output is which rankings to trust, not a "perfect" order. A seeded PRNG (mulberry32) makes runs reproducible so a review can rerun the exact numbers.
- **Greedy packing with dependency passes** is easy to explain in a planning meeting. An exact knapsack would squeeze in slightly more value, but nobody could follow why item #7 jumped ahead.
- **The LLM writes prose, not rankings.** It gets only the computed facts as JSON and a "no new facts" instruction. `TemplateLLM` produces the same structure offline.
- No dependencies: Node's built-in test runner and `fetch`.

## Run
```bash
npm test                     # 12 tests (node:test via tsx)
npm run demo                 # 2 quarters × 6 person-months
npm run demo -- 8 3          # 3 quarters × 8 person-months
ANTHROPIC_API_KEY=... npm run demo
```

## Next steps
- Value of information: estimate how much a better reach estimate would change the expected roadmap value.
- Pull reach directly from product analytics instead of hand estimates.
- Add a strategic-theme constraint (e.g. at least 30% of capacity on platform work).
