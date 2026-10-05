# IT Ticket Routing

Route incoming IT tickets to the right resolver queue (network, access, hardware, software, security) with a TF-IDF nearest-centroid classifier. Each decision comes with a confidence and margin, and anything the model isn't sure about falls back to human triage.

```text
$ python -m ticket_routing
train 200 tickets, test 88 (8 off-topic, half the rest use unseen phrasings)

router               auto-routed  acc routed  end-to-end  misroutes  off-topic caught
keyword rules                70%         95%         66%          3               88%
tf-idf centroid              84%         99%         82%          1               88%

threshold sweep (min similarity): fewer misroutes cost more human triage
  0.00  auto  85%  misroutes  1  off-topic caught  88%
  0.06  auto  85%  misroutes  1  off-topic caught  88%
  0.12  auto  84%  misroutes  1  off-topic caught  88%
  0.18  auto  75%  misroutes  1  off-topic caught 100%
  0.24  auto  51%  misroutes  1  off-topic caught 100%
  0.30  auto  25%  misroutes  0  off-topic caught 100%

sample decisions
  security  0.33/+0.33  clicked a link in an email and now outlook is acting weird  (matched on email, clicked, link)
  access    0.27/+0.18  VPN says my account is not authorized  (matched on says, not, authorized)
  hardware  0.17/+0.08  the coffee machine on the 3rd floor is broken  (matched on broken, coffee, floor)
  hardware  0.23/+0.07  my laptop screen is flickering after the update  (matched on laptop, screen, flickering)
```

## Why it matters
A 2,000-person company opens about 1,500 IT tickets a month. If a dispatcher spends 2 minutes reading and assigning each one, that's 50 hours a month. A misrouted ticket is worse: it sits in the wrong queue for hours, and when it's a phishing report, that delay is the difference between one compromised mailbox and twenty. On held-out phrasings, the centroid router sends 84% of in-scope tickets straight to a resolver queue with 99% accuracy, and makes 1 misroute against 3 for keyword rules. The threshold sweep is the operating dial for the service desk manager: push the threshold up during a security incident to route fewer tickets automatically and have more of them read by a person.

Why not an LLM: routing is a five-way choice made thousands of times a month, labels already exist in the ticket history, and the decision has to be explainable to the resolver teams. A centroid model trains in milliseconds, costs nothing per ticket and shows which words drove each decision. An LLM is better spent drafting the first reply once the ticket is in the right queue.

## Architecture
```
ticket text ──► tokens(): lowercase, drop desk filler ("pls", "asap", "ticket"), + bigrams
                    ▼
               TfIdf: sublinear tf × smoothed idf, min_df=2, L2-normalized sparse dicts
                    ▼
               cosine vs one centroid per queue (mean of its training vectors)
                    ▼
       best < 0.12 ? ──► triage ("no queue is similar enough")
       best − 2nd < 0.06 ? ──► triage ("too close to call vs access")
                    ▼
               queue + score + margin + explain() terms
```
- **Nearest centroid instead of k-NN or a deep model.** Five queues with many short, repetitive tickets is exactly where Rocchio works well. It is a single dot product per queue, and retraining on last month's tickets is instant.
- **Two gates, two failure modes.** Low similarity catches off-topic or novel tickets ("parking gate stuck"). Low margin catches tickets between two queues ("VPN says my account is not authorized" is network vs access).
- **Metrics follow what the desk feels.** Auto-route rate (dispatcher hours saved), accuracy when routed, end-to-end, raw misroute count (the expensive error), and the share of off-topic tickets caught.
- **Known gap, shown honestly.** "Coffee machine is broken" still lands in hardware because "broken" is a strong hardware word. That's an argument for a small "facilities" queue in the training data, not for a cleverer model.

## Run
```bash
pip install pytest
python -m pytest -q                         # 15 tests
python -m ticket_routing                    # evaluate and show sample decisions
python -m ticket_routing "outlook keeps asking for my password" "printer jammed on 4"
python -m ticket_routing.synth              # regenerate data/train.csv and data/test.csv
```

## Next steps
- Retrain nightly from resolver reassignments: every ticket moved between queues is a free corrected label.
- Add a priority model (P1-P4) alongside the queue, with security keywords allowed to escalate on their own.
- Watch per-queue centroid drift so a new application or outage shows up as a shift in vocabulary.
