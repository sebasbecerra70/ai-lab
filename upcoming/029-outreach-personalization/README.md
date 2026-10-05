# Outreach Personalization

Has an LLM draft a first-touch email for each prospect from a fact sheet, then runs every draft through a **deterministic eval suite**: length, personalization, banned claims, invented numbers, a single call to action, an opt-out line and readability. Failed checks go back to the model as reviewer feedback until the email passes or the loop gives up.

```text
$ python -m outreach Lucia
Drafting 6 emails with MockLLM; each draft must pass 9 checks

prospect                             attempts  first-draft failures -> final
Dana @ Northstar Fresh                      2  no banned claims (guarantee) -> PASS
Rahul @ Veridian Biologics                  1  none -> PASS
Lucia @ Atlantic Catch                      2  numbers grounded (unsupported: 12%); readable (24.2 words/sentence (max 24)) -> PASS
Tom @ Harvest Lane Foods                    2  numbers grounded (unsupported: 12%) -> PASS
Aiko @ PureDose Pharmacy Network            1  none -> PASS
Marcus @ Glacier Dairy Co-op                2  one call to action (3 questions) -> PASS

first-draft pass rate 2/6; after revise loop 6/6
first-draft failures by check: no banned claims 1, numbers grounded 2, one call to action 1, readable 1

--- final email to Lucia Ferreira ---
Subject: Cold chain at Atlantic Catch

Hi Lucia,

I saw that Atlantic Catch posted a job for a cold chain compliance manager. Teams in seafood import often tell us the hard part after a move like that is slow response when reefer containers drift out of range.

We work with a seafood importer that reduced excursion response time from 4 hours to 20 minutes, using lane-level excursion analytics to find the carriers and docks that cause spoilage.

Would a 20-minute call next week be useful to see whether the same approach fits Atlantic Catch?

Maya Ortiz
Account Executive, Coldline Analytics
Reply 'no thanks' and I won't follow up.
```

## Why it matters
An SDR team sending 200 personalized emails a day can't read every LLM draft, and only one bad one needs to reach a prospect. An email that "guarantees results" or quotes an invented "12% inventory loss" can kill an enterprise deal, or create a compliance problem in pharma, where marketing claims are regulated. The suite turns "looks fine to me" into nine pass/fail gates that run in milliseconds. In the sample run, **4 of 6 first drafts fail** (a hype guarantee, two invented statistics, a rambling triple ask), and the revise loop brings all 6 to a pass in one extra call each. A sales leader can track the first-draft pass rate per prompt or model version the same way an engineering team tracks a test suite.

## Architecture
```
data/prospects.json ─┐
data/product.json ───┴─► build_prompt: FACTS json (prospect + approved proof points + banned claims)
                                 │
                                 ▼
                       LLMClient.complete(SYSTEM, prompt)
                       ├─ AnthropicClient (urllib, claude-sonnet-5-5) when ANTHROPIC_API_KEY is set
                       └─ MockLLM: deterministic; injects real failure modes on some first drafts
                                 │
                                 ▼  parse_email (tolerates prose and code fences)
                       run_checks ── subject · length 60-140 words · personalized (name, company, trigger)
                                     no placeholders · no banned claims · numbers grounded in FACTS
                                     one call to action · opt-out line · ≤24 words/sentence
                                 │
                       failed? ──yes──► REVIEWER FEEDBACK + previous draft ─► LLM (max 2 revisions)
                                 │no
                                 ▼
                         send-ready email + per-attempt eval history
```
- **Rules, not an LLM judge, for the hard gates.** Each check is a regex or a count, so it is cheap, explainable, and gives the same verdict every time, which matters when Legal signs off on the banned-claims list. An LLM judge is a good addition for tone, but should not be the only gate on a compliance claim.
- **Number grounding catches hallucinated proof.** Every number in the email must appear in the fact sheet. That one check catches the most damaging LLM failure in sales copy: a confident statistic nobody can source.
- **Feedback names the failed check.** The revision prompt lists exactly what failed and says "change nothing else", which keeps the fix targeted. A full rewrite would often reintroduce a different problem.
- **The mock is adversarial on purpose.** A mock that always writes perfect emails would never exercise the loop. Hashing the prospect's name picks a realistic flaw for 4 of the 6 prospects, so tests and the offline demo cover the failure path deterministically.
- **Bounded loop.** After 2 revisions a draft that still fails is returned as FAIL with its history, for a human to fix. It is never sent.
- Standard library only.

## Run
```bash
pip install pytest
python -m pytest -q                         # 10 tests
python -m outreach                          # offline, MockLLM
python -m outreach Rahul                    # print a specific prospect's final email
ANTHROPIC_API_KEY=... python -m outreach    # real drafts from Claude
```
Edit `data/product.json` (proof points, banned claims, call to action, footer) and `data/prospects.json` (one row per prospect with a trigger event and a pain point).

## Next steps
- Add an LLM-as-judge check for tone and relevance, calibrated against 50 emails that SDR managers have rated.
- Log reply rates per email and correlate them with each check, to find which rules actually move replies.
- Generate follow-up emails 2 and 3 with a "no repeated proof point" check across the sequence.
