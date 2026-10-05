# Incident Postmortem Generator

Merges raw syslog lines and the incident chat channel into one de-duplicated timeline, computes detect / acknowledge / mitigate / resolve times, and has an LLM draft a **blameless** postmortem from those facts only. A linter then checks the draft for blame language, timestamps that aren't in the evidence, and missing sections.

```text
$ python -m postmortem
timeline: 37 raw events -> 33 after collapsing repeats

  02:03:40  [change    ] cfg-mgmt: change CHG-4471 applied: firmware 3.2.1 on pdu-b2 by change-bot
  02:14:05  [fault     ] pdu-b2: breaker B2-3 trip, outlets 13-24 de-energized
  02:14:06  [fault     ] r14-host07 (+2 more): power supply PSU2 lost input
  02:14:07  [fault     ] r14-host10 (+1 more): power supply PSU1 absent, host down
  02:14:40  [fault     ] checkout: 5xx rate 18.2% (threshold 2%)
  02:16:02  [alert     ] alertmanager: page sent: CheckoutErrorRateHigh to oncall-sre
  02:16:40  [ack       ] priya: ack CheckoutErrorRateHigh, looking
  02:19:10  [mitigation] priya: triggering manual failover db-07 -> db-08
  02:24:30  [mitigation] marcus: checkout errors back under 1%. mitigated. leaving SEV1 open until power is understood
  ...
metrics: time_to_detect=1m57s, time_to_acknowledge=2m35s, time_to_mitigate=10m25s, time_to_resolve=47m55s
suspected trigger: change CHG-4471 applied: firmware 3.2.1 on pdu-b2 by change-bot

----- draft (MockLLM) -----
# Postmortem: Checkout errors after PDU breaker trip in row 14
## Summary
At 02:14:05 a fault began (pdu-b2: breaker B2-3 trip, outlets 13-24 de-energized). Customers saw errors until mitigation at 02:24:30; ...
## Root cause and contributing factors
- Trigger (suspected): change CHG-4471 applied: firmware 3.2.1 on pdu-b2 by change-bot, shortly before the first fault.
- r14-host10 and host11 were running on PSU2 only; PSU1 was pulled for an RMA and never replaced, so the B-feed trip took them fully down
## What was hard
- The first page (CheckoutErrorRateHigh to oncall-sre) came from a customer-facing symptom 1m57s after the first fault on pdu-b2, which paged no one.
- Database failover needed a human to trigger it.
## Action items
- [P1] Canary PDU firmware on one non-critical PDU with a 24h soak before fleet rollout (owner: facilities engineering)
- [P1] Daily check for hosts running on a single PSU; block RMA tickets from closing until the part is reinstalled (owner: DC operations)
- [P2] Page directly on PDU breaker-trip events instead of waiting for customer-facing error rates (owner: SRE)
- [P2] Make db failover automatic when the primary's host loses power (owner: database team)
-----
lint: PASS  blame=[] ungrounded_times=[] missing_sections=[]
```

## Why it matters
A SEV1 postmortem typically takes an incident commander 3–5 hours, and most of that is rebuilding the timeline: scrolling Slack, grepping logs, lining up timestamps. That delay is why postmortems slip a week and action items lose their urgency. This tool builds the timeline and metrics in seconds, so the human time goes into the part that matters: deciding what to change.

The sample incident shows why the structure matters. The interesting facts aren't "the breaker tripped". They're that **a firmware change landed 10 minutes earlier**, that **two hosts had been running on one PSU since an RMA**, and that **the breaker trip paged no one**. Detection waited about two minutes for customer errors. Those are three systemic fixes. A blame-oriented write-up ("tech didn't replace the PSU") would have produced one reprimand and none of them.

## Architecture
```
data/syslog.log ─┐   parse_logs / parse_chat
data/chat.jsonl ─┴─► merge by time ─► classify (rules: change, fault, alert, ack, declare, comms,
                                       │                  finding, mitigation, decision, resolved)
                                       ▼
                     collapse(): same message within 60s → one event with N sources
                                       ▼
                     compute_metrics(): first fault → detect/ack/mitigate/resolve; change ≤ 60 min before fault
                                       ▼
data/roles.json ──► build_facts(): names → roles, retro bullets and action items derived by rules
                                       ▼
                     LLMClient (MockLLM | AnthropicLLM) with a blameless, facts-only system prompt
                                       ▼
                     lint(): blame phrases · timestamps not in FACTS · required sections
```
- **Deterministic first, LLM last.** Parsing, metrics, trigger detection and action-item candidates are plain code you can test. The LLM only turns verified facts into readable prose, which is the part it's good at, and it has nothing to invent.
- **Blameless by construction.** Names are swapped for roles before the model ever sees them, the system prompt bans "should have" and "human error", and the linter checks the output anyway. That's three layers, because blame language is the thing that kills postmortem culture.
- **Grounding check on times.** Any HH:MM in the draft that isn't in the facts fails lint. Hallucinated timestamps are the most common and most damaging error in auto-generated incident reports.
- **Collapse, don't drop.** Repeated log lines become one event with a host count ("r14-host07 (+2 more)"). The timeline gets shorter without losing blast-radius information.
- **Trade-off:** the classification rules are keyword-based and tuned to this log vocabulary. A new log source means new rules. That's predictable and cheap compared with an ML classifier, and the rules list is the single place to extend.

## Run
```bash
python -m pytest -q                            # 15 tests, offline
python -m postmortem                           # timeline + mock draft + lint
python -m postmortem --timeline-only
ANTHROPIC_API_KEY=... python -m postmortem     # Claude writes the draft; lint still runs
```

## Next steps
- Pull events directly from Slack, PagerDuty and Loki/Splunk APIs instead of files.
- Link action items to tickets and track closure rate per quarter.
- Use a fault-tree view: correlate faults with the rack/PDU topology (see the alert triage project).
- Add an LLM-as-judge pass that scores drafts on clarity and actionability against past approved postmortems.
