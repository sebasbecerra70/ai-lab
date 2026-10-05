# PRD Drafter

A product-requirements assistant in three steps: a **structured interview** that pushes back on vague answers, an **LLM that fills a fixed PRD template** using only what the PM said, and a **completeness checker** that scores any PRD (drafted here or written by hand) for missing sections, unmeasurable goals and fuzzy requirements.

```text
$ npm run demo
interview:
  Q(problem): What problem does this solve, for whom, and what evidence do you have?
  A: Printing labels is slow.
  -> follow-up needed
  Q(problem): Say more: who has the problem, how often, and what it costs them (aim for 25+ words).
  A: Shipping clerks at mid-size warehouses print carrier labels one order at a time. At peak a...
  Q(goals): How will we know it worked? List metrics with a baseline and a target.
  A: - Faster label printing (+more)
  -> follow-up needed
  Q(goals): These metrics have no number; give a baseline and target: Faster label printing; Fewer tickets
  A: - Median time to print a 50-order wave: 11 min -> under 2 min (+more)
  ...
----- PRD (TemplateLLM) -----
# PRD: Bulk label printing
## Goals and success metrics
- Median time to print a 50-order wave: 11 min -> under 2 min
- Label-printing support tickets: 140/month -> under 40/month within 60 days of GA
## Requirements
- P0: Select up to 200 orders from the order list and print all labels as one PDF in under 30 seconds
- P0: Show which orders failed (address invalid, carrier error) and let the clerk retry just those
...
drafted PRD: completeness 100/100, 0 gap(s)

data/weak-prd.md: completeness 0/100, 13 gap(s)
  [blocker] Users: section is missing
  [blocker] Non-goals: section is missing
  [blocker] Risks and open questions: section is missing
  [major] Acceptance criteria: contains a placeholder (TBD)
  [major] Problem: no evidence: add a number (tickets, churn, hours, revenue)
  [major] Goals and success metrics: not measurable: "Better engagement"
  [major] Requirements: no P0 requirement; launch scope is undefined
  [minor] Requirements: vague word "Seamless" without a number: "Seamless mobile experience"
  ...
```

## Why it matters
Most PRD problems are omissions, not bad writing. There's no baseline on the metric, no non-goals, and "fast" with no number. Engineering then finds those gaps in sprint planning, or worse, in QA. A missing non-goal is how a two-sprint feature turns into a quarter. An unmeasurable goal means nobody can say afterwards whether the feature worked.

The interview catches gaps while the PM is still thinking ("These metrics have no number; give a baseline and target"). The checker gives reviewers an objective first pass, so a 30-minute PRD review is about trade-offs, not "what does success look like?". On the sample, the same feature idea goes from "Faster label printing" to "11 min → under 2 min, 140 → under 40 tickets a month", which is something an engineering lead can size and a VP can hold the team to.

## Architecture
```
 PM (REPL or scripted answers)
        │
        ▼
 Interview.run()  ── 8 questions, each with check(answer) → follow-up | null (max 2 follow-ups)
        │ answers JSON
        ▼
 draftPrd(llm)    ── PRD_SYSTEM: fixed sections, keep every number, no invention,
        │            Given/When/Then for each P0, unknowns → Risks and open questions
        │            LLMClient: TemplateLLM (offline) | AnthropicLLM (fetch, ANTHROPIC_API_KEY)
        ▼
 checkPrd(md)     ── sections present/non-empty · placeholders · problem evidence ·
                     measurable goals · P0 exists · vague words · criteria per P0
                     → score 0-100 (blocker −20, major −10, minor −4) + gap list
```
- **Validate at the source.** Checks live on the questions, so vague input is challenged while the PM can still fix it, not reported later in review.
- **The LLM formats, it doesn't decide.** The template and the "keep every number, invent nothing" rule make the model a writer, not a product strategist. Missing facts become open questions instead of plausible fiction.
- **The checker works on any Markdown PRD.** It doesn't depend on the drafter, so a team can run it in CI on a `docs/prd/` folder or as a pre-review gate.
- **Deterministic, explainable rules.** Every deduction names its section and reason. An LLM grader could catch subtler issues, but a PM can argue with a rule and can't argue with a vibe. An LLM pass is listed as a next step.
- **Bug the tests caught:** the "0" in "P0" originally counted as a number, so "P0: make it seamless" passed the vagueness check. Priority tags are now stripped before the check.

## Run
```bash
npm test        # 15 tests (node:test via tsx)
npm run demo    # scripted interview -> PRD -> checks; uses Claude if ANTHROPIC_API_KEY is set
```

## Next steps
- Add an interactive REPL mode (`readline`) for a live interview.
- Add an LLM review pass for consistency (do the requirements actually serve the stated goals?).
- Pull problem evidence automatically from support-ticket tags and CRM loss reasons.
- Export to Notion or Confluence, and track how the score changes across PRD revisions.
