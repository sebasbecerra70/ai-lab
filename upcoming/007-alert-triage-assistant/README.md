# Alert Triage Assistant

Turns a night's worth of raw monitoring alerts into a short list of incidents. It **dedupes repeats, correlates alerts through the rack/PDU/switch topology, assigns a SEV level and names a root-cause candidate**, then drafts the on-call handover with an LLM.

```text
$ python -m alert_triage
28 alerts -> 16 deduped groups -> 5 incidents

SEV1 (score 12) root cause: PDU-B2  start 02:14:05  alerts 11
    PDU-B2   pdu_input       x1  critical
    web-01   psu_redundancy  x1  warning
    web-02   psu_redundancy  x1  warning
    app-05   psu_redundancy  x1  warning
    app-06   psu_redundancy  x1  warning
    PDU-B2   pdu_load        x1  critical
    app-06   host_down       x1  critical
    app-05   host_down       x1  critical
    web-01   http_5xx        x2  critical
    web-02   http_5xx        x1  critical
SEV2 (score 5) root cause: tor-r14  start 02:30:00  alerts 7
    tor-r14  interface_flap  x5  major
    cache-02 latency_high    x1  warning
    log-01   packet_loss     x1  warning
SEV2 (score 5) root cause: CRAC-4  start 02:40:00  alerts 2
    CRAC-4   supply_temp     x2  major
SEV3 (score 3) root cause: db-07  start 01:02:10  alerts 6
    db-07    disk_usage      x6  warning
SEV4 (score 1) root cause: batch-03  start 01:40:00  alerts 2
    batch-03 cpu_high        x2  warning

On-call summary:
- SEV1 since 02:14:05: 11 alerts, likely cause PDU-B2; impact: checkout (tier 1), orders-api (tier 1). First action: dispatch DC tech to the PDU, confirm feed A status with facilities, shed load if feed B > 80%.
- SEV2 since 02:30:00: 7 alerts, likely cause tor-r14; impact: logging (tier 3), session-cache (tier 2). First action: check the uplink optic/cable on the ToR, fail traffic to the redundant uplink.
- SEV2 since 02:40:00: 2 alerts, likely cause CRAC-4; impact: no customer-facing services yet. First action: page facilities for the CRAC, check rack inlet temps, open contingency cooling.
- SEV3 since 01:02:10: 6 alerts, likely cause db-07; impact: orders-db (tier 1). First action: check the host and recent changes.
- Can wait until morning: batch-03 (batch-03:cpu_high x2).
```

## Why it matters
During an incident, the on-call engineer gets paged by every layer at once: the PDU, IPMI on each server, ping checks, and app 5xx alarms. In this sample that's 28 alerts in 30 minutes, which reduce to **one** SEV1 caused by one PDU. Reading them in arrival order means the root cause gets found 10–15 minutes later, while checkout returns 5xx errors. Collapsing them into 5 ranked incidents, with "dispatch DC tech to PDU-B2" as the first line, cuts time-to-acknowledge and keeps a repeating disk warning from paging anyone at 2 a.m.

## Architecture
```
alerts.json ─► dedupe (host+check, 30-min gap) ─► 16 groups
                                │
topology.json ─► upstream(host) = {PDU, ToR switch, CRAC}
                                │
          correlate: union-find over groups that overlap in time (±5 min)
                     AND share a host or an upstream device that is ITSELF alerting
                                │
          root cause = alerting infra device, else earliest signal
                                │
          score: raw severity + tier-1 availability impact + blast radius
                 + infra category (power/cooling/network) + persistence → SEV1..4
                                │
          incident_facts (JSON) ─► LLMClient ─► on-call summary
                                  (TemplateLLM offline | Claude)
```
- **Rules and topology do the triage; the LLM writes the summary.** Correlation and severity must be deterministic and auditable, since they decide who gets paged. The LLM only turns structured facts into readable handover text, and its prompt forbids going beyond those facts.
- **Correlate only through components that are alerting.** Every host in hall B shares a CRAC, and merging on that alone would produce one giant incident. Requiring the shared device to be alerting itself is a simple heuristic that is easy to explain.
- **Fingerprint on host + check, not message text.** Messages change on every repeat ("86%" → "87%", "up" → "down"), so a message-based key would never dedupe a flapping link.
- **Explainable severity.** Each incident's score is a sum of named points, so a disputed SEV can be argued against a rule rather than a model.
- **Trade-off:** the 5-minute correlation window can merge two unrelated failures that happen together. The correlation tests cover both the merge and the separate cases.

## Run
```bash
pip install pytest
python -m pytest -q                     # 10 tests
python -m alert_triage                  # sample night
ANTHROPIC_API_KEY=... python -m alert_triage
```

## Next steps
- Learn correlation edges from incident history (which alerts co-occur) to supplement the static topology.
- Suppress child alerts at the source once a root cause is acknowledged.
- Post the summary to Slack/PagerDuty and track MTTA before and after.
