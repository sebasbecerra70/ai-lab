# Competitive Intel Digest

Diff each competitor's pricing and web pages between two snapshots, classify and rank every change, and have an LLM write a cited digest with a "so what" for each competitor. A citation audit makes sure every high-severity change made it into the digest.

```text
$ python -m intel_digest
19 changes across 3 competitors: 9 high, 7 medium, 3 low

  C1  high   hivemetric plan_added      new Scale plan at $599/month
  C2  high   hivemetric feature_added   Business gains Warehouse sync
  C3  high   hivemetric feature_added   Team gains Warehouse sync
  C4  high   relaydesk  feature_added   Enterprise gains AI reply drafts
  C5  high   relaydesk  feature_added   Enterprise gains Data residency (EU)
  C6  high   relaydesk  price_increase  Starter: $15/mo -> $19/mo (+27%)
  C7  high   relaydesk  price_increase  Growth: $39/mo -> $45/mo (+15%)
  C8  high   relaydesk  feature_added   Growth gains AI reply drafts
  C9  high   relaydesk  positioning     home tagline: "The shared inbox for fast-growing support teams." -> "The AI-first help desk for fast-growing support teams."
  C10 medium hivemetric limit_change    Free dashboards: 3 -> 10 (more generous)
  C11 medium hivemetric limit_change    Free events_m: 1 -> 5 (more generous)
  C12 medium hivemetric copy_added      home: + "Sync to Snowflake and BigQuery with Warehouse sync."
  C13 medium relaydesk  limit_change    Growth automations: 50 -> 100 (more generous)
  C14 medium relaydesk  claim_change    home: "Trusted by 2,000+ teams including Brightline and Northwind." -> "Trusted by 2,500+ teams including Brightline, Northwind and Cobalt Foods."
  C15 medium relaydesk  copy_added      home: + "AI reply drafts resolve routine tickets in seconds, trained on your help center."
  C16 medium relaydesk  copy_added      home: + "Now with EU data residency for regulated industries."
  C17 low    hivemetric feature_added   Free gains Alerts
  C18 low    hivemetric limit_change    Team events_m: 20 -> 25 (more generous)
  C19 low    opsforge   claim_change    home: "We are hiring: 4 open roles." -> "We are hiring: 7 open roles."

=== digest ===
## hivemetric
- new Scale plan at $599/month [C1]
- Business gains Warehouse sync [C2]
- Team gains Warehouse sync [C3]
- Free dashboards: 3 -> 10 (more generous) [C10]
- Free events_m: 1 -> 5 (more generous) [C11]
- home: + "Sync to Snowflake and BigQuery with Warehouse sync." [C12]
So what: hivemetric now matches our differentiators (Warehouse sync) [C2] [C3] [C12]; added a plan to capture a new segment [C1].

## relaydesk
- Enterprise gains AI reply drafts [C4]
- Enterprise gains Data residency (EU) [C5]
- Starter: $15/mo -> $19/mo (+27%) [C6]
- Growth: $39/mo -> $45/mo (+15%) [C7]
- Growth gains AI reply drafts [C8]
- home tagline: "The shared inbox for fast-growing support teams." -> "The AI-first help desk for fast-growing support teams." [C9]
- Growth automations: 50 -> 100 (more generous) [C13]
- home: "Trusted by 2,000+ teams including Brightline and Northwind." -> "Trusted by 2,500+ teams including Brightline, Northwind and Cobalt Foods." [C14]
- home: + "AI reply drafts resolve routine tickets in seconds, trained on your help center." [C15]
- home: + "Now with EU data residency for regulated industries." [C16]
So what: relaydesk now matches our differentiators (AI reply drafts, Data residency (EU)) [C4] [C5] [C8] [C15]; Starter is now $1 above our Starter price [C6]; Growth is now $3 above our Growth price [C7].

citation audit: passed
```

## Why it matters
Competitors change pricing and positioning quietly, and BD usually finds out from a prospect in a late-stage deal ("RelayDesk just added AI drafts and EU residency"). By then you're defending instead of positioning. A weekly digest that takes seconds to produce changes that. In the sample, the important signals stand out from 19 raw changes: RelayDesk raised Growth to $45, now $3 above our $42. Their Starter tier jumped 27%. They repositioned from "shared inbox" to "AI-first help desk" and now match two of our differentiators. That's enough for a battlecard update and a targeted offer to their price-sensitive Starter customers the same week. The hiring-count tweak and the whitespace edit are ranked low or filtered out, so nobody spends time on them.

## Architecture
```
data/prev/<competitor>/{pricing.json, *.md}     data/curr/<competitor>/{pricing.json, *.md}
                       └──────────────────┬──────────────────┘
                                          ▼
 pricing_diff(): plans ± | price Δ% (≥5% = high) | features ± (on our watch list = high) | limits
 page_diff():    clean_lines() drops "updated N days ago", cookies, ©, whitespace
                 difflib line opcodes → positioning (tagline) | claim_change (numbers) | copy ± / changed
                                          ▼
 diff_all(): sort by severity, assign ids C1..Cn
                                          ▼
 build_prompt(changes, us.json: differentiators + our prices) ──► LLMClient (Mock | Claude)
                                          ▼
 audit(): cited ids must exist; every high-severity change must be cited
```
- **Structure first, prose last.** Pricing is diffed as data, not text, so "+27%" is computed, never guessed. The LLM only summarizes and explains a change list that has already been verified.
- **Severity rules encode BD priorities.** Price moves of 5% or more, new or removed plans, tagline changes and features that hit our differentiators are high. Social-proof numbers and new copy are medium. Hiring counts are low. The rules are short and readable so the team can tune them.
- **Noise filtering is half the value.** Timestamps, cookie banners and whitespace churn would otherwise drown the digest. They're dropped before diffing.
- **Citations make the digest auditable.** Every bullet points at a change id, and the audit fails if the model invents an id or skips a high-severity change. That's what makes it safe to forward to sales.

## Run
```bash
pip install pytest
python -m pytest -q                          # 10 tests
python -m intel_digest                       # sample snapshots, mock LLM
python -m intel_digest snapshots/last snapshots/this
ANTHROPIC_API_KEY=... python -m intel_digest
```

## Next steps
- Add a fetcher that snapshots pricing pages on a schedule and extracts plan tables into `pricing.json`.
- Track changes over time per competitor to spot strategy shifts (three AI features in a quarter, not just one).
- Push high-severity changes to the matching battlecard and alert the owners of open deals against that competitor.
