# Sales Call Summarizer

Reads sales call transcripts, pulls out the six **MEDDIC** fields with a verbatim customer quote behind each one, rejects any quote that the customer never said, and turns the result into a deal-health score with risks and next actions.

```text
$ python -m call_summarizer
== Harbor Clinics (Negotiation, $140,000)  health 95/100 HEALTHY
  + metrics           confirmed   "The pilot showed we can defer one cooling upgrade, that is about 400 thousand "
  + economic_buyer    confirmed   "I own the budget and I sign, it's within my authority."
  + decision_criteria confirmed   "We need HIPAA language in the DPA and single sign-on with Okta, both were chec"
  + decision_process  confirmed   "Legal has the redlines, we want to sign by end of quarter so the rollout start"
  + identify_pain     confirmed   "The pain is real though, we lost two days of a clinic floor to a cooling failu"
  + champion          confirmed   "Maria, our facilities lead, is the internal champion, she presented the pilot "
  risks: timeline risk raised on the call

== Northwind Labs (Evaluation, $180,000)  health 90/100 HEALTHY
  + metrics           confirmed   "Roughly 240 thousand dollars in emergency colo fees, plus a delayed product la"
  + economic_buyer    confirmed   "Our CFO, Mark Ellis, approves anything over 100k."
  + decision_criteria confirmed   "Integration with our DCIM is a must, it has to support our Schneider PDUs, and"
  + decision_process  confirmed   "Technical validation with my team over three weeks, then security review, then"
  + identify_pain     confirmed   "Right now we plan rack space and power in spreadsheets and we were caught shor"
  + champion          confirmed   "Honestly I'm pushing this internally because I don't want to explain another c"
  risks: competing with Sunbird

== Cobalt Foods (Discovery, $95,000)  health 13/100 AT RISK
  ~ metrics           partial     "Things are just slow, lots of manual work."
  ! economic_buyer    unverified  "Our finance director owns this budget and will sign."  <- quote not found in transcript
  ~ decision_criteria partial     "It needs to be easy to use, we are not very technical."
  - decision_process  missing
  ~ identify_pain     partial     "We have some issues with planning."
  ~ champion          partial     "My manager asked me to look at tools."
  risks: competing with Nlyte, Sunbird; no budget allocated; single-threaded: one customer contact; timeline risk raised on the call
  behind for Discovery: identify_pain
  next: Find the business event behind the interest; 'it's slow' is not a pain.
  next: Quantify the pain: ask what the problem cost last year in dollars or hours.
  next: Get introduced to the budget owner; ask who signed the last purchase of this size.

pipeline $415,000, health-weighted $307,350
```

## Why it matters
Forecast calls run on the rep's gut. A $415k pipeline looks like $415k until somebody asks "who signs?" and "what does it cost them not to buy?". In the sample, Cobalt Foods is in the forecast at $95k, but the only contact is an analyst who was asked to "look at tools". There is no budget, no quantified pain and two competitors. The summarizer marks it at risk (13/100) and gives the three questions to ask on the next call. Weighted by health, the pipeline is about $307k rather than $415k.

The evidence check matters just as much. LLM extraction that says "economic buyer: confirmed" with a quote that is not in the transcript is worse than nothing, because a manager will trust it. The demo has the mock model invent a quote on the Cobalt call ("Our finance director owns this budget and will sign."). The verifier catches it, shows it as `unverified` and gives it no credit.

## Architecture
```
data/calls/*.txt ─► transcript.load()   header (deal, stage, amount) + turns, seller vs customer
                          │
                          ▼
                 build_prompt()  ─► LLMClient.complete()   MockLLM (cue phrases, offline)
                          │                                AnthropicLLM (stdlib HTTP, if ANTHROPIC_API_KEY)
                          ▼
                 extract(): parse JSON ─► quote_in() per field ─► confirmed / partial / missing / unverified
                          │                stakeholders() regex ─► single-threaded?
                          ▼
                 score(): weighted MEDDIC coverage x risk multipliers
                          │  stage gaps (what this stage should have confirmed) ─► next actions
                          ▼
                 CLI report + health-weighted pipeline
```
- **The LLM proposes and code verifies.** The model must quote the customer exactly. `quote_in` normalizes punctuation and whitespace, then checks for a span in *customer* turns only, so a rep's leading question can't count as evidence. A failed check becomes `unverified`, not `confirmed`.
- **The score is transparent.** Weights (economic buyer and pain at 20, the rest at 15) times status credit (confirmed 1.0, partial 0.4), then multiplicative risk penalties: competitors (capped at 20%), no budget (20%), single-threaded (15%), timeline risk (5%). A sales leader can argue with the numbers, which they can't do with a black-box probability.
- **Gaps are judged against the stage.** A Discovery call is only expected to find the pain. A Negotiation deal missing a decision process is a real problem. Next actions put stage gaps first.
- **Single-threading is detected deterministically.** Named people the customer mentions ("Sam from facilities", "CFO, Mark Ellis") count as extra contacts. That is cheap, explainable and works without the model.
- **The mock is honest about being a mock.** It uses cue-phrase matching over customer sentences, which is enough to exercise the full pipeline offline and in tests. The real client sends the same prompt to `claude-sonnet-5-5`.
- **Why not a trained classifier?** There are three transcripts and no labels. Extraction with verified quotes works from day one, and the verified fields become the training labels later.

## Run
```bash
pip install pytest
python -m pytest -q                                   # 11 tests
python -m call_summarizer                             # all calls in data/calls, offline mock
python -m call_summarizer data/calls/cobalt_intro.txt
ANTHROPIC_API_KEY=... python -m call_summarizer       # real model
```
Transcript format: first line `DEAL: <name> | stage: <Discovery|Evaluation|Negotiation> | amount: <n>`, then `Speaker: text` lines. The seller's first line is written `AE (Name): ...`.

## Next steps
- Track MEDDIC per deal across calls so a field confirmed in call 1 stays confirmed in call 3, and flag fields that regress.
- Calibrate the weights against closed-won and closed-lost history with logistic regression.
- Push the fields and the health score to CRM opportunity fields, and post next actions to the deal channel.
