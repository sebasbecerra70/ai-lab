# Model Router

Send each prompt to the cheapest model that can handle it: a small logistic-regression difficulty classifier picks a small or large model, and an evaluator reports the cost vs. quality frontier so you can choose the threshold.

```text
$ python -m model_router
classifier: train acc 100%, holdout acc 92%; top features [('reasoning_words', 1.12), ('log_words', 0.98), ('clauses', 0.79)]

policy           $/day @100k   quality   %large
always-small             244    80.2%      0%
always-large             488    95.3%    100%
oracle                   440    94.7%     42%
router@0.20              440    94.7%     42%
router@0.35              401    91.8%     33%
router@0.50              401    91.8%     33%
router@0.65              401    91.8%     33%
router@0.80              401    91.8%     33%

p_hard=0.02 -> small: [small] answer to: Convert 12 pounds to kilograms.
p_hard=1.00 -> large: [large] answer to: Design a rollout plan for a new pricing tier and
```

## Why it matters
Most production LLM traffic is easy: lookups, reformatting, short classifications. If every request goes to the large model, you pay large-model prices for work a model at half the price handles just as well. In the sample run, routing at a 0.2 threshold matches the oracle (the large model only on truly hard prompts). It cuts spend by 10% and gives up only 0.6 points of quality on the holdout set, while always-small saves 50% but drops acceptable answers to 80%. At 100k requests a day that's about $18k a year from a classifier that adds well under a millisecond per request. The gap grows with longer hard-prompt outputs or a pricier large tier. The frontier table gives a product owner a clear choice: how much quality do we trade for each dollar?

## Architecture
```
prompt ──► features.extract()  (length, reasoning verbs, code/constraint hints, clauses)
              │
              ▼
     DifficultyClassifier (logistic regression, standardized features, L2)
              │  p_hard
              ▼
     Router(threshold) ──► small tier  (MockLLM | claude-haiku-4-5)
              │        └─► large tier  (MockLLM | claude-sonnet-5-5)
              ▼
     evaluate()/frontier(): $/day @100k requests, expected quality, % sent large
```
- **A classical classifier, not an LLM judge.** The router has to cost much less than the money it saves, so it uses 8 interpretable features and logistic regression trained from scratch. `top_features()` shows what drives each decision.
- **Quality is modeled per tier.** Each `ModelTier` carries list prices (Haiku 4.5 and Sonnet 5.5) and acceptance rates on easy and hard prompts. Replace the illustrative numbers with results from your own eval set, and the frontier updates on its own.
- **Threshold as a business knob.** Lowering the threshold sends more traffic to the large model. The sample run shows the failure mode: a short but hard prompt ("Prove that every tree...") scores p=0.30, so a 0.5 threshold misroutes it. A lower threshold catches it at higher cost.
- **The LLM boundary** is a one-method protocol. Tests use `MockLLM`; when `ANTHROPIC_API_KEY` is set, the CLI calls Haiku for the small tier and Sonnet for the large tier.

## Run
```bash
pip install pytest
python -m pytest -q                                   # 10 tests, offline
python -m model_router "Summarize this ticket" "Design a sharded queue and explain trade-offs"
ANTHROPIC_API_KEY=... python -m model_router "your prompt"
```

## Next steps
- Label real production prompts by whether the small model's answer passed an LLM-as-judge check, and retrain on that.
- Add a cascade policy: try the small model first and escalate when a confidence or format check fails.
- Track the router's calibration drift weekly and alert when the share sent large moves by more than 10 points.
