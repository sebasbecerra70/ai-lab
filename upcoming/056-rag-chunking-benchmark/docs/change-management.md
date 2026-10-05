# Change Management

All changes to production go through the change process so that risky changes are reviewed, scheduled and reversible.

## Change types

### Standard changes
Pre-approved, low risk and repeatable changes, such as scaling a service within its approved limits or rotating a certificate. These need no review meeting and can be executed at any time by the owning team.

### Normal changes
These need a peer review and approval from the change advisory board. The board meets every Tuesday and Thursday. A normal change request must be submitted at least 2 business days before the planned date.

### Emergency changes
These fix an active incident or an urgent security issue. They are approved by the incident commander or the on-call engineering manager, and are reviewed retroactively at the next board meeting.

## Freeze windows

Production changes are frozen from the 20th of December to the 3rd of January, and during the last 3 business days of each fiscal quarter. Only emergency changes are allowed during a freeze. A freeze exception needs approval from the VP of Engineering.

## Rollback

Every normal change must include a tested rollback plan. If health checks fail within 15 minutes of a deployment, the change is rolled back automatically. A change that is rolled back twice needs a new review before it can be attempted again.

## Deployment windows

Normal changes to customer-facing services are deployed between 10:00 and 16:00 local time on weekdays, so the full team is available. Database schema changes are deployed on Tuesday or Wednesday only.
