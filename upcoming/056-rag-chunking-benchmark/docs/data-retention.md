# Data Retention

This policy defines how long each class of data is kept and how it is deleted. Retention periods start from the date the record was created unless stated otherwise.

## Customer data

Customer account data is kept for the life of the contract plus 90 days. After the grace period, data is deleted from primary storage, and backups age out within a further 35 days. Customers can request an export at any time before deletion.

## Logs

### Application logs
Kept in hot storage for 30 days and in cold storage for 1 year. They must not contain passwords, tokens or full card numbers, and a scanner blocks deploys that log such fields.

### Audit logs
Kept for 7 years to meet financial and SOC 2 requirements. They are write-once and cannot be deleted by any engineer, including administrators.

## Backups

Production databases are backed up every 6 hours. Daily snapshots are kept for 35 days and monthly snapshots for 13 months. A restore test is run every quarter, and the measured restore time is recorded against the 4 hour recovery time objective.

## Legal hold

When legal places a hold on data, all deletion for the affected records stops until the hold is released in writing. Legal holds override every other retention period in this policy.

## Employee records

Personnel files are kept for 6 years after the employee leaves. Interview notes for candidates who were not hired are deleted after 12 months.
