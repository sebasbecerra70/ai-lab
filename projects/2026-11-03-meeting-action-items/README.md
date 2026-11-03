# Meeting Action Items

Turns raw meeting notes into **owners, due dates and decisions**. An LLM does the extraction, and every item it returns is **validated against the notes**: the evidence must be quoted verbatim, the owner must be an attendee, and the date must parse. A **regex extractor** acts as the fallback when the model is down and as a cross-check for items it missed. The output is a Markdown checklist for the follow-up email or a CSV for the tracker.

```text
$ npm run demo
LLM: RecordedLLM

## Fulfillment ops weekly (Mon 02 Mar), extracted by llm

Decisions:
- Move two receivers from the AM to the PM shift starting Monday 9 March
- No new SKUs go to the mezzanine until pick accuracy is back above 99.5%

Action items:
- [ ] Jen Okafor: Roll back the mezzanine slotting change and re-measure pick accuracy (due Fri 06 Mar)
- [ ] Marco Diaz: Close the dock 4 door repair ticket (due Mon 09 Mar)
- [ ] Priya Shah: Confirm the overtime budget with finance (due Thu 05 Mar)
- [ ] Sam Lee: Send the carrier scorecard to the team (due Mon 09 Mar)
- [ ] UNASSIGNED: Investigate label printer jams on line 2 (no due date)
  1 item(s) need an owner or a date before this goes out
  warning: "Investigate label printer jams on line 2": owner "Maintenance" is not an attendee, left unassigned
  warning: dropped "Update the shift roster in the WFM tool": evidence not found in the notes

## Packaging vendor QBR - Corrugated Supply Co. (Wed 04 Mar), extracted by regex

Decisions:
- We will move to a weekly forecast share instead of monthly
- Price stays flat through Q3 if on-time recovers to 97%

Action items:
- [ ] Alex Romero: Schedule the next QBR for early June (no due date)
- [ ] Beth Nguyen: Set up the weekly forecast share in the supplier portal (due Wed 11 Mar)
- [ ] Dana Kim: Draft the updated SLA with a 96% floor and send it to legal (due Fri 20 Mar)
- [ ] Luis Ortega: Send a root-cause report on the two late deliveries (due Fri 06 Mar)
  1 item(s) need an owner or a date before this goes out
  warning: LLM failed (no recorded response for "Packaging vendor QBR - Corrugated Supply Co."); used regex fallback
```

## Why it matters
The cost of a meeting is mostly in what happens after it. An operations team that meets 10 times a week and loses one action item per meeting drops about 500 commitments a year, and the dropped ones are usually the vague ones: "someone should look into the printer jams". This tool turns that line into an explicit **UNASSIGNED** item that has to be resolved before the recap goes out. It also refuses to make up work: in the sample, the model returned a plausible "update the shift roster" task that nobody said, and the evidence check removed it. When the API is down, the vendor QBR recap still goes out from the regex path with the same owners and dates.

## Architecture
```
data/notes/*.md ─► parseNotes: title, Date:, Attendees: (role tags stripped), body
                         │
                         ├─────────────────────────────► regexExtract (always runs)
                         │                                 Decision:/Agreed/We decided → decisions
                         ▼                                 ACTION:/TODO, "Name will/to/owns", @handle,
         LLMClient.complete(EXTRACT_SYSTEM, prompt)        "someone should" → unassigned
         ├─ AnthropicLLM (fetch, claude-sonnet-5-5)        DUE_PATTERN + resolveDue (weekday, next X,
         └─ RecordedLLM (replays real responses)            EOW/EOM, 3/9, March 20)
                         │                                         │
                         ▼                                         │
         validate: evidence verbatim in notes? owner an attendee?  │
                   due parses and ≥ meeting date?                  │
                         │                                         │
             ok ─────────┴─► Result(source=llm) + possibleMisses ◄─┘ (regex hits the LLM didn't return)
             throw / bad JSON / bad schema ─► Result(source=regex)
                         │
                         ▼
          toChecklist (grouped by owner, UNASSIGNED last, gaps + warnings) · toCSV (tracker import)
```
- **The LLM proposes and the code validates.** Models are good at "Marco owns the ticket, needs it closed by 3/9", which is an owner, a task and a date in one messy sentence. They also invent tasks that sound plausible. Requiring a verbatim evidence quote turns each hallucination into a dropped item with a warning.
- **Regex as fallback and cross-check.** The regex extractor is less flexible but predictable. It keeps the tool working during an outage and catches LLM omissions (`possibleMisses`) without a second model call.
- **Dates are resolved against the meeting, in UTC.** "By Thursday" written on Monday means this Thursday, "by Monday" said on a Monday means next week, and "for early June" is an event date rather than a deadline, so it is deliberately not parsed as one.
- **Recorded responses instead of a hand-written mock.** `RecordedLLM` replays real model output (including its mistakes), so tests cover the validation path against realistic failures. Any meeting without a recording looks like an outage, which demos the fallback.
- No dependencies: Node's built-in test runner, `fetch` and `tsx`.

## Run
```bash
npm test                         # 11 tests (node:test via tsx)
npm run demo                     # checklists for every file in data/notes/
npm run demo -- --csv            # CSV for a tracker import
ANTHROPIC_API_KEY=... npm run demo
```
Drop new notes into `data/notes/` with a `# Title`, `Date: YYYY-MM-DD` and `Attendees:` header.

## Next steps
- Post the checklist to the meeting's Slack thread, and DM each owner their items with a due-date reminder.
- Carry open items forward: match next week's notes against last week's checklist and mark items done or slipped.
- Measure extraction precision and recall on 30 hand-labelled meetings to compare prompts and models.
