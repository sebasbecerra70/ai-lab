# Log Anomaly Detection

Compress raw data center syslog into event templates with a Drain-style parser, then flag the three kinds of change that matter: event types never seen before, bursts of known events, and regular events from a host that went silent. Related signals are grouped into a single incident.

```text
$ python -m log_anomaly
2,347 lines -> 12 templates (baseline 00:00-04:00, 10-minute windows)

  T2     510  sensor <*> reading <NUM> C ok
  T1     478  fan <*> speed <NUM> RPM ok
  T0     412  heartbeat seq=<NUM> ok
  T4     220  Interface Ethernet1/<NUM> link up, speed <NUM>
  T6     191  BGP neighbor <IP> keepalive received
  T5     141  session opened for user svc_monitor from <IP>
  T7     130  session closed for user svc_monitor from <IP>
  T8     102  outlet <NUM> current <NUM> A within limit
  T10     76  PSU2 input voltage <NUM> V out of range, failing over to PSU1
  T3      48  Interface Ethernet1/<NUM> link down
  T9      29  SEL log <NUM> full
  T11     10  outlet <NUM> current <NUM> A above warning threshold

for comparison, a keyword alert (fail|error|down|warning) fires 37 times in the quiet baseline hours

29 anomalous (window, template) signals -> 1 incident(s)

INCIDENT 04:20-06:00
  NEW    T10 PSU2 input voltage <NUM> V out of range, failing over to P  76 lines, never seen in baseline  [r13-bmc]
  NEW    T11 outlet <NUM> current <NUM> A above warning threshold        10 lines, never seen in baseline  [pdu-a3]
  SILENT T0  heartbeat seq=<NUM> ok                                      0 lines for 8 windows (baseline 2.0/window)  [r13-bmc]
  SILENT T2  sensor <*> reading <NUM> C ok                               0 lines for 6 windows (baseline 2.8/window)  [r13-bmc]
  SILENT T1  fan <*> speed <NUM> RPM ok                                  0 lines for 5 windows (baseline 2.0/window)  [r13-bmc]
  SILENT T7  session closed for user svc_monitor from <IP>               0 lines for 2 windows (baseline 0.8/window)  [r13-bmc]
  BURST  T1  fan <*> speed <NUM> RPM ok                                  105 lines over 2 windows (baseline 10.8/window)  [r10-bmc, r11-bmc, r12-bmc, r14-bmc, r15-bmc]
```

## Why it matters
A single data hall produces millions of BMC, switch and PDU log lines a day. Keyword alerting on "fail|error|down" is how most NOCs start, and in this sample it fires 37 times in four quiet hours, mostly on routine link flaps. Operators learn to ignore it. The detector instead reduces 2,347 lines to 12 templates, raises nothing on a generated day with no incident, and here opens one incident at 04:20 that tells the whole story: rack 13's PSU2 starts failing over (a new event type), its neighbors' fans spin up (a burst), a PDU outlet crosses its warning threshold, and r13's BMC stops sending heartbeats (silence). That's one page with the probable cause in the first line, instead of thirty-seven tickets and a missed PSU failure that turns into a rack outage when PSU1 also fails.

Why not an LLM: this runs on every line in real time, has to be cheap and deterministic, and its output (templates, rates, probabilities) is easy to audit. An LLM fits well downstream, summarizing one incident's templates into a ticket.

## Architecture
```
"04:21:07 r13-bmc PSU2 input voltage 162 V out of range, failing over to PSU1"
          ▼ split timestamp / host / message
   mask(): IPs → <IP>, hex → <HEX>, numbers with units (25G, 85%) → <NUM>
          ▼
   Drain tree: token count → first 3 tokens (digit-bearing tokens → <*> branch) → leaf clusters
          ▼ similarity ≥ 0.5 ? merge (differing positions → <*>) : new template
   Event(sec, host, template id)
          ▼ 10-minute windows, baseline = first 4 hours
   NEW    template unseen in baseline
   BURST  (x − μ)/√(μ+1) ≥ 4  and  x ≥ 3μ
   SILENT per (template, host): p0 = P(empty window in baseline); flag when p0^run < 1e-4
          ▼
   incidents(): anomalies in consecutive windows → one incident
```
- **Drain's fixed-depth tree is why it's fast.** Each line is compared only with the few clusters in its leaf, not with every template. It's online, so new templates appear the moment they occur, which is what "new event type" detection needs.
- **Silence is about regularity, not rate.** A heartbeat that's never missed a window trips after three empty windows. A noisy sensor that's sometimes quiet needs a much longer gap. That one rule removed the false positives a fixed "zero for N windows" rule produced.
- **Per-host silence, global bursts.** A dead host shows up as its own regular events stopping. Fan bursts are a fleet-level signal, so they're counted across hosts.
- **Tested for false positives.** A generated six-hour log with no incident must produce zero anomalies. That's the test that keeps a NOC from muting the tool.

## Run
```bash
pip install pytest
python -m pytest -q                 # 9 tests
python -m log_anomaly               # sample syslog with an injected PSU incident
python -m log_anomaly /var/log/dc/syslog.txt
python -m log_anomaly.loggen        # regenerate data/syslog.txt
```

## Next steps
- Use a rolling baseline (same hour last week) so daily batch jobs don't look like bursts.
- Persist the Drain tree between runs and version templates, so "new" means new to the fleet, not new to this file.
- Correlate incidents with the DCIM topology (same rack, same PDU, same power path) to rank probable causes.
