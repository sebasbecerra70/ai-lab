# LLM-as-Judge with Bias Checks

Uses an LLM to grade other LLM outputs: pairwise ("which answer is better?") and against a rubric (1–5 per criterion). Every judgement is checked before anyone trusts it. Answers are swapped to catch position bias, the output must parse strictly, and the judge is measured against human labels with Cohen's kappa and Spearman correlation.

```text
$ python -m llm_judge
judge: MockJudge

pairwise (A shown first, then B shown first):
  p01  fwd=A   bwd=A   final=A   human=A
  p02  fwd=B   bwd=B   final=B   human=B
  p03  fwd=A   bwd=B   final=tie human=tie  <- flipped with order
  ...
  p09  fwd=A   bwd=B   final=tie human=tie  <- flipped with order
  p12  fwd=A   bwd=B   final=tie human=tie  <- flipped with order

  flip rate on swap            25%
  first-position win rate      62%  (50% = no position bias)
  agreement, single pass       58%
  agreement, swap-consistent   83%  (kappa 0.73)

rubric (1-5):
  r01  corr=5 comp=5 conc=5 tone=4  overall=4.75  human=5
  r02  corr=2 comp=1 conc=5 tone=2  overall=2.50  human=2
  ...
  r07  corr=5 comp=5 conc=4 tone=4  overall=4.50  human=3
  r08  corr=2 comp=1 conc=5 tone=4  overall=3.00  human=3

  Spearman rho vs human overall: 0.90
```

## Why it matters
Teams shipping LLM features need to compare prompts and models on hundreds of examples per change, and human review doesn't scale to that. A support team rating 500 answers at 2 minutes each spends about 17 hours per release. An LLM judge does it in minutes for a few dollars, but **only if its verdicts can be trusted**. Judges have known failure modes: they prefer whichever answer they see first, they like longer answers, and they sometimes return unparseable text.

This harness puts numbers on those failure modes. On the sample set, a single-pass judge agrees with humans 58% of the time. Asking twice with the order swapped, and calling it a tie when the verdicts disagree, raises that to 83% (kappa 0.73, "substantial" agreement). That's the difference between a metric you can gate a release on and one you can't. Row r07 shows the remaining verbosity bias: a rambling, hedged answer still scores 4.5 against a human 3, which is exactly the kind of thing a calibration set is for.

## Architecture
```
data/pairs.jsonl (q, reference, a, b, human)        data/rubric_set.jsonl (q, reference, answer, human 1-5)
          │                                                     │
          ▼                                                     ▼
  judge_pair(): ask(A,B) + ask(B,A)                    judge_rubric(): 4 criteria, JSON only,
  consistent? winner : "tie"                           ints 1-5 enforced, 1 retry on bad output
          │                                                     │
          ▼                                                     ▼
  pairwise_report(): flip rate, first-position          spearman(judge overall, human overall)
  win rate, agreement single vs swapped, kappa
                       ▲
          LLMClient ── MockJudge (offline, deliberately position-biased) | AnthropicLLM (ANTHROPIC_API_KEY)
```
- **Swap and require consistency.** It costs 2× the calls but removes the most common judge bias. Inconsistent verdicts become ties, not coin flips, so they lower confidence instead of adding noise.
- **Measured, not assumed.** "First-position win rate" is the bias detector: 50% is unbiased, and 62% here shows the effect. Kappa is used instead of raw agreement because with three labels, chance agreement is already about 33%.
- **The reference answer goes in the prompt.** The judge grades against known-good facts, not its own knowledge. That's what catches the invented "Pro includes SSO" answer in p04.
- **Strict parsing with one retry.** Scores must be integers from 1 to 5 for exactly the rubric's criteria. Anything else is retried once, then raised. Silently defaulting to 3 would hide judge failures inside the averages.
- **A deliberately flawed mock.** The offline `MockJudge` is a lexical-overlap scorer with a built-in position bias. That keeps the tests deterministic, and it proves the bias checks actually detect bias.

## Run
```bash
python -m pytest -q                         # 11 tests, offline
python -m llm_judge                         # mock judge
ANTHROPIC_API_KEY=... python -m llm_judge   # Claude as the judge
```

## Next steps
- Add a length-controlled comparison (truncate or normalize length) to measure verbosity bias directly.
- Use a multi-judge panel (different models) with majority vote, and report inter-judge kappa.
- Bootstrap confidence intervals on agreement, since 12 pairs is a smoke test, not a calibration set.
- Write judge verdicts to a store and alert when agreement on a weekly human-labelled sample drifts.
