# Runbook Q&A

Ask a data center runbook question at 3 a.m. and get the exact procedure as numbered steps, each one cited to the runbook line it came from. Requests to skip a safety control are refused with the rule that forbids them, and questions no runbook covers get "escalate" instead of a guess.

```text
$ python -m runbook_qa
Q: A PDU breaker tripped in row C, what do I do?
-> answered (llm)
   1. Identify the tripped breaker and affected racks from the DCIM power view. [power_distribution#pdu-breaker-trip:1]
   2. Confirm affected servers failed over to their B-side power supplies. [power_distribution#pdu-breaker-trip:2]
   3. Check the rack's power draw history for overload before the trip. [power_distribution#pdu-breaker-trip:3]
   4. Do not reset a breaker more than once; a second trip indicates a fault that needs an electrician. [power_distribution#pdu-breaker-trip:4]
   5. Reset the breaker once, then watch the branch current for 15 minutes. [power_distribution#pdu-breaker-trip:5]
   6. If the circuit was overloaded, move load to another circuit and update the rack power budget. [power_distribution#pdu-breaker-trip:6]

Q: The breaker keeps tripping, can I reset it again?
-> refused (guard)
   I can't help with repeatedly resetting a tripped breaker. The runbook says: "Do not reset a breaker more than once; a second trip indicates a fault that needs an electrician." [power_distribution#pdu-breaker-trip:4]

Q: How do I remove another tech's lock so I can finish the job?
-> refused (guard)
   I can't help with defeating lockout/tagout. The runbook says: "Never bypass or remove another person's lock." [power_distribution#lockout-tagout-for-electrical-work:4]

Q: How do I renew the SSL certificate on the customer portal?
-> not_covered (retriever)
   No runbook covers this. Escalate to the shift lead.

Validator check with a hallucinating model: ['unknown citation [power_distribution#pdu-breaker-trip:99]'] -> served extractive answer
```

## Why it matters
Most data center outages that turn into customer-facing incidents involve human error during a response, not the original fault. A night-shift technician three months into the job, facing a UPS-on-battery alarm, has to find the right binder, the right page and the one line that says "under 10 minutes of runtime, start load shedding." That takes minutes they may not have. An assistant that returns the procedure in seconds helps, but only if it never invents a step. One hallucinated "power-cycle the row" could drop a 2 MW hall. So this design favors traceability over fluency: every step is cited, unverifiable answers are replaced with the verbatim runbook, and safety-control bypasses are refused before the model is consulted.

## Architecture
```
question ──► guard.check() ── unsafe intent? ──► REFUSE + quote the "do not / never" step it violates
                │ safe
                ▼
       BM25 over procedures (one per "## " heading, title-weighted, bigrams)
                │ score < 2.0 or < 2 shared terms ──► NOT COVERED: escalate to shift lead
                ▼ top-2 procedures, every step tagged [doc#procedure:n]
       LLMClient.complete()  (MockLLM offline | Claude when ANTHROPIC_API_KEY is set)
                ▼
       validate(): every numbered line cited? every citation in the retrieved set?
                ├── yes ──► answer (source=llm)
                └── no  ──► verbatim runbook steps (source=extractive) + logged problems
```
- **Retrieval unit = one procedure.** Runbooks are short and sequential, so returning half a procedure is worse than returning a whole one. Headings get double weight, and bigrams that keep stopwords separate "UPS on battery" from "UPS battery string".
- **Step-level citation IDs.** `[power_distribution#pdu-breaker-trip:4]` lets a reviewer check any line in one click. It also gives the validator something exact to check, which free-text quotes would not.
- **The guard is rules, not the model.** Bypass requests (lockout/tagout, repeated breaker resets, opening batteries in thermal runaway, skipping approvals) match explicit patterns that a facilities manager can review. The refusal quotes the runbook's own prohibition, so the reason is the site's policy, not the bot's opinion.
- **Fail closed, not silent.** If the model's answer fails validation, the tech still gets the correct steps verbatim, and the problems are recorded so model quality can be tracked.
- **Abstain on weak matches.** A single shared word ("portal") is not coverage. Questions below the score and term thresholds are routed to a human.

## Run
```bash
pip install pytest
python -m pytest -q                                     # 13 tests, offline
python -m runbook_qa                                    # demo questions with the mock LLM
python -m runbook_qa "chilled water leak under row D"
ANTHROPIC_API_KEY=... python -m runbook_qa "UPS on battery, generator not starting"
```

## Next steps
- Track runbook versions and refuse to answer from a procedure past its review date.
- Log every question that gets "not covered" and send the list to the runbook owners as a gap report.
- Add a short-form mode that returns only the first three actions, for radio or phone handoffs.
