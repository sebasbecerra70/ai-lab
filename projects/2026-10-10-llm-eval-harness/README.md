# LLM Eval Harness

A small, dependency-free harness for testing LLM features the way you'd test any other code. Test cases are plain JSON (no YAML DSL). There are four kinds of grader: exact, contains, regex/JSON shape, and per-criterion LLM-as-judge. The output is a pass-rate report with **regression detection against a baseline and a CI gate**.

```text
$ python -m llm_eval
pass rate: 75% (9/12)
by tag:    format 3/3  policy 4/5  safety 3/4  tone 0/1
by grader: contains 4/5  exact 1/1  json_keys 1/1  llm_judge 2/3  regex 1/2
failures:
  - sla-hours [contains]: none of ['1 hour', 'one hour', '60 minutes'] present
  - tone-apology [llm_judge]: #1 not met: must apologize; #3 not met: must be one sentence
  - no-made-up-discount [regex]: matched forbidden /(?i)code:\s*[A-Z0-9]{5,}/
vs baseline 75%: regressions ['sla-hours'], fixes ['pii-refusal']
gate (>= 80%, no regressions): FAIL

```

## Why it matters
Changing a prompt or upgrading a model is a deploy. Without evals, teams find regressions from customer complaints. In the run above, overall pass rate held at 75% vs the baseline, but **the SLA answer silently regressed** (a support bot now promises "4 hours" for P1) while a PII case got fixed. An average hides that kind of swap, so the gate fails on any regression, not just on the threshold. The report also shows *what* failed (missing phrase, rubric criterion #1, forbidden pattern), so the fix is obvious.

## Architecture
```
data/cases.json ──► load_cases (unique ids)
                         │
            ┌────────────┴─────────────┐
            ▼                          ▼
    system under test            grader per case
    LLMClient.complete     exact | contains(all/any/none) | regex(+must_not)
    (ReplayLLM | Claude)   json_keys | llm_judge(rubric → per-criterion JSON verdicts)
            └────────────┬─────────────┘
                         ▼
             Report: pass rate, by tag, by grader, failures
                         │
         baseline.json ──┴─► regressions / fixes ──► gate (exit code for CI)
```
- **Use the cheapest grader that works.** Most product requirements are checkable with string or regex rules, which are free, instant and never flaky. The LLM judge is reserved for tone and safety rubrics that rules can't express.
- **The judge returns one verdict per criterion, not a 1–10 score.** Binary checks per criterion are more repeatable and tell you exactly what to fix. Malformed judge output or a mismatched verdict count **fails closed**.
- **Recorded outputs.** `ReplayLLM` grades saved generations, so changing a grader or rubric doesn't cost a full regeneration run. `--live` regenerates outputs with Claude at temperature 0.
- **A crashing grader is a failed case**, not a crashed run. One bad regex in case 47 shouldn't hide the other 99 results.
- **`KeywordJudge`** is a deterministic offline judge so the tests and demo need no API key. The real judge prompt is the same one Claude gets.

## Run
```bash
pip install pytest
python -m pytest -q                          # 11 tests
python -m llm_eval                           # grade recorded outputs; exit 1 if the gate fails
python -m llm_eval --save-baseline           # accept current results as the new baseline
ANTHROPIC_API_KEY=... python -m llm_eval --live
```

## Next steps
- Sample each case N times at temperature > 0 and report flakiness (pass@k).
- Calibrate the LLM judge against 50 human-labeled outputs and report agreement (see project 016).
- Add cost and latency per case to the report.
