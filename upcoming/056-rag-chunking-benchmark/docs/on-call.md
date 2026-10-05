# On-Call

Every production service has a primary and a secondary on-call engineer. Rotations are one week long and hand over on Monday at 10:00 local time.

## Expectations

### Primary
Acknowledges pages within 10 minutes, day or night, and has a laptop and network access within 30 minutes. Works only on interrupts during the shift; planned project work is paused.

### Secondary
Backs up the primary and takes over if a page is not acknowledged. Must be reachable but does not need to stay near a laptop. Takes over the full shift if the primary is sick.

## Compensation

Engineers receive a flat stipend of 300 dollars for each week on the primary rotation and 150 dollars for each week as secondary. A page between 22:00 and 07:00 earns a time-off credit of 2 hours, capped at 1 day per week. Credits must be used within 60 days.

## Handoff

The outgoing primary writes a handoff note listing open incidents, noisy alerts and anything that was silenced. The incoming primary reads it and confirms in the on-call channel before 11:00. Silenced alerts older than 7 days are reviewed at the handoff and either fixed or deleted.

## Alert hygiene

An alert that pages more than 5 times in a week without action is a noisy alert. The owning team must fix or delete noisy alerts within 2 weeks. Every paging alert must link to a runbook.
