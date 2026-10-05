# Change Risk Scorer

Scores data center change requests on **likelihood × impact** for the Change Advisory Board (CAB). Impact comes from simulating the failure through a power, cooling, network and service dependency graph. The scorer also checks timing, rollback and overlapping changes, and gives each request a recommendation (standard, approve, approve with conditions, CAB review, or reject) with the specific conditions attached.

```text
$ python -m change_risk
Failure rate by change type (Beta(1,9) smoothed): software-deploy 15%, power-maintenance 14%, firmware 13%, hardware-swap 5%, config 4%

CAB agenda: 8 changes
change    when              P(fail)  L  I  risk  recommendation
CHG-1046  Wed 30 Dec 02:00      15%  4  5    21  REJECT / RESCHEDULE
CHG-1041  Sun 15 Nov 01:00      14%  4  3    12  REJECT / RESCHEDULE
CHG-1042  Sun 15 Nov 02:00       5%  2  3     6  REJECT / RESCHEDULE
CHG-1044  Tue 17 Nov 14:00      26%  5  5    27  REJECT: reduce risk first
CHG-1048  Sun 22 Nov 01:00      14%  4  4    16  CAB REVIEW
CHG-1043  Wed 18 Nov 02:00      13%  4  3    12  CAB REVIEW
CHG-1045  Sun 22 Nov 03:30       4%  2  3     6  STANDARD (pre-approved)
CHG-1047  Wed 18 Nov 02:30       5%  2  3     6  APPROVE WITH CONDITIONS

CHG-1046 Database primary major version upgrade [software-deploy] -> REJECT / RESCHEDULE
  blast radius if it fails: billing-api
  loses redundancy: customer-portal
  BLOCKER: inside quarter-end close freeze until Mon 04 Jan
  BLOCKER: irreversible change with service impact
  condition: move into a maintenance window
  condition: no rollback: get a restore point and a go/no-go checkpoint signed off
  condition: no work on db-replica during the change (sole path for customer-portal)
  condition: no work on pdu-A2 during the change (sole path for customer-portal)
  condition: no work on rack-03 during the change (sole path for customer-portal)

CHG-1041 UPS-B battery string replacement [power-maintenance] -> REJECT / RESCHEDULE
  blast radius if it fails: pdu-B1, pdu-B2
  loses redundancy: crah-1, crah-2, rack-01, rack-02
  BLOCKER: overlaps CHG-1042: together they take down billing-api, customer-portal
  condition: no work on pdu-A1 during the change (sole path for billing-api, customer-portal)
  condition: no work on pdu-A2 during the change (sole path for billing-api, customer-portal)
  condition: no work on ups-A during the change (sole path for billing-api, customer-portal)

CHG-1042 PDU-A1 breaker swap [hardware-swap] -> REJECT / RESCHEDULE
  blast radius if it fails: target only
  loses redundancy: rack-01, rack-02
  BLOCKER: overlaps CHG-1041: together they take down billing-api, customer-portal
  condition: no work on pdu-B1 during the change (sole path for billing-api, customer-portal)
  condition: no work on ups-B during the change (sole path for billing-api, customer-portal)

CHG-1044 Storage array controller firmware [firmware] -> REJECT: reduce risk first
  blast radius if it fails: backup-svc, billing-api, customer-portal, db-primary, db-replica, reporting
  condition: move into a maintenance window (currently during peak hours)
  condition: rehearse the 120-min rollback before the window
  condition: peer review of the implementation plan

CHG-1048 Rack-03 PDU-A2 maintenance [power-maintenance] -> CAB REVIEW
  blast radius if it fails: backup-svc, db-replica, rack-03, reporting
  loses redundancy: crah-1, crah-2, customer-portal
  condition: no work on pdu-B2 during the change (sole path for billing-api, customer-portal)
  condition: no work on ups-B during the change (sole path for billing-api, customer-portal)

CHG-1043 Core switch 1 firmware 9.3.12 [firmware] -> CAB REVIEW
  blast radius if it fails: target only
  loses redundancy: firewall-ha, storage-array
  condition: rollback would overrun the window: start earlier or shorten scope
  condition: no work on core-sw-2 during the change (sole path for billing-api, customer-portal)
  condition: overlaps CHG-1047 (no joint outage, but share the bridge call)

CHG-1045 Reporting service config: new export job [config] -> STANDARD (pre-approved)
  blast radius if it fails: target only

CHG-1047 CRAH-1 fan bearing replacement [hardware-swap] -> APPROVE WITH CONDITIONS
  blast radius if it fails: target only
  loses redundancy: rack-01, rack-02, rack-03
  condition: no work on crah-2 during the change (sole path for billing-api, customer-portal)
  condition: overlaps CHG-1043 (no joint outage, but share the bridge call)
```

## Why it matters
Industry outage surveys consistently find that a large share of data center outages trace back to changes and procedures rather than to equipment failure. The costly ones are usually two changes that were each low-risk. In the sample agenda, the UPS-B battery job and the PDU-A1 breaker swap would each pass a typical CAB: dual-corded racks, tested rollback, a Sunday window. Scheduled in overlapping hours, though, they **de-energize both feeds to rack-01 and take down billing and the customer portal**. A spreadsheet risk matrix cannot see that because it scores each change on its own. Simulating the overlap catches it before the window, at no cost.

It also cuts CAB time. The routine reporting config change is marked **STANDARD (pre-approved)**, so the board can spend its hour on the storage firmware planned for Tuesday 14:00, which has no peer review and an unrehearsed 2-hour rollback.

## Architecture
```
data/topology.json ─► Node(depends_on = groups of alternatives)
                       │   rack-01: [[pdu-A1, pdu-B1], [crah-1, crah-2]]  = dual feed, N+1 cooling
                       ▼
  simulate(targets) ─► fixed point: a node is down when any group is all down
                       ├─► blast radius (down), lost redundancy (degraded)
                       └─► single_points_of_failure: one extra failure → customers down
                                                       (only SPOFs the change creates)
data/history.csv ──► failure_rates: Beta(1,9) posterior per change type (rollback = failure)
                       ▼
  likelihood band 1-5 = rate × no-staging 1.5 (software only) × no-peer-review 1.3 × targets
  impact band 1-5     = customers down 5 / shared infra 4 / single path or one service 3 / degraded 2
data/calendar.json ─► window, peak hours (+1/+2), freezes (blocker), rollback must fit the window
                       ▼
  check_collisions: overlapping changes are simulated *together*
                       ▼
  recommend: blockers → REJECT/RESCHEDULE, risk ≥20 reject, ≥12 CAB review, conditions → approve w/ conditions,
             low-risk tested config → STANDARD
```
- **Graph simulation instead of a "criticality" field.** Hand-assigned criticality goes stale the day someone re-cords a rack. The topology file says what is plugged into what, and the blast radius follows from it. Redundancy groups model dual-corded loads, N+1 cooling and HA pairs in one consistent way.
- **Only new SPOFs are reported.** `firewall-ha` is always a single point of failure in this site, and repeating that on every change trains people to ignore the warning. The scorer lists only the exposure a specific change creates, and each one becomes a "no work on X" condition.
- **Smoothed failure history.** Firmware has 20 past changes and power maintenance only 12. A Beta(1,9) prior keeps a type with few records from looking either perfectly safe or alarming. Rolled-back changes count as failures.
- **Hard rules beat scores for some things.** Freezes, irreversible changes with service impact, and joint outages are blockers regardless of score. A risk score shouldn't be able to argue its way past a quarter-end freeze.
- **Why not ML or an LLM?** There are too few failed changes to train on, and a CAB needs a reason it can audit for every flag. An LLM could write the CAB summary from these findings, but the findings themselves must be deterministic.
- Standard library only.

## Run
```bash
pip install pytest
python -m pytest -q                      # 9 tests
python -m change_risk                    # full CAB agenda
python -m change_risk CHG-1041 CHG-1042  # just the colliding pair
```
Model your site in `data/topology.json`, export past changes from the ITSM tool into `data/history.csv`, and put upcoming requests in `data/changes.json`.

## Next steps
- Pull the topology from DCIM (power chain) and CMDB (service dependencies) instead of maintaining it by hand.
- Use the measured duration of past changes of the same type to flag windows that are too short, not just rollbacks that overrun.
- Suggest the earliest conflict-free window automatically for each rejected change.
