# Contract Clause Extractor

Read partner and vendor contracts, find the clauses that matter to a deal desk (renewal, termination, liability, indemnity, payment, governing law), extract their key terms, and flag risk against policy. An LLM does the classification, and deterministic rules validate it and take over whenever the model's output is unusable.

```text
$ python -m clause_extractor
== cobalt_marketplace (we are Seller)  risk score 14
  §2  payment          [llm  ] days=60
  §3  renewal          [llm  ] auto_renew=True, renewal_months=12, notice_days=30
  §4  termination      [llm  ] convenience_parties=['marketplace'], any_time=True
  §5  liability        [llm  ] uncapped_parties=['seller']
  §6  indemnification  [llm  ] mutual=False, indemnitor=seller, broad_scope=True
  §7  governing_law    [rules] jurisdiction=Netherlands
  ! HIGH   §4: marketplace can terminate at any time without notice
  ! HIGH   §5: our liability is uncapped
  ! HIGH   §6: one-way indemnity owed by us with broad scope
  ! MEDIUM §2: 60-day payment terms (policy max 45)
  ! MEDIUM §7: foreign governing law: Netherlands
  ! LOW    §3: auto-renewal: add to the renewal calendar
  note: LLM output rejected for §7; used rules

== acme_reseller (we are Partner)  risk score 13
  §3  payment          [llm  ] days=90
  §4  renewal          [llm  ] auto_renew=True, renewal_months=12, notice_days=120
  §5  termination      [llm  ] convenience_parties=['vendor'], notice_days=30, any_time=False
  §6  confidentiality  [llm  ] survival_months=60
  §7  liability        [rules] cap_months=3, uncapped_parties=['partner']
  §8  indemnification  [llm  ] mutual=False, indemnitor=partner, broad_scope=True
  §9  governing_law    [llm  ] jurisdiction=Delaware
  ! HIGH   §5: only vendor can terminate for convenience
  ! HIGH   §7: our liability is uncapped
  ! HIGH   §8: one-way indemnity owed by us with broad scope
  ! MEDIUM §4: auto-renews with 120-day notice window (policy max 60)
  ! MEDIUM §7: counterparty cap only 3 months of fees (policy min 12)
  note: LLM output rejected for §7; used rules

== brightline_msa (we are Client)  risk score 0
  §2  payment          [llm  ] days=30
  §3  renewal          [llm  ] auto_renew=False
  §4  termination      [llm  ] convenience_parties=['either'], notice_days=60, any_time=False
  §5  liability        [llm  ] cap_months=12
  §6  indemnification  [llm  ] mutual=True, indemnitor=each, broad_scope=False
  §7  confidentiality  [rules] survival_months=36
  §8  governing_law    [llm  ] jurisdiction=New York
  note: LLM output rejected for §7; used rules
```

## Why it matters
A BD team signing 30-50 partner agreements a year can't send every redline to legal, and the expensive mistakes are always the same few clauses. One example is a 120-day non-renewal window nobody calendared, which locks you into another year of a $200k reseller commitment. Another is uncapped liability for the partner while the vendor caps theirs at three months of fees. A third is a marketplace that can delist you at any time. In the sample, this triage takes seconds per contract. It ranks the marketplace terms (score 14) and the reseller agreement (13) as needing legal review, and clears the MSA (0) for standard approval. That lets legal spend its time on the two contracts that need it.

## Architecture
```
contract.txt ──► split_clauses() numbered sections ──► our_role() ("Partner", "Seller"...)
                        │ per clause
          ┌─────────────┴──────────────┐
          ▼                            ▼
   LLMClient.complete()           classify() regex rules
   (Mock | Claude) → JSON              │
          │ parse_llm(): JSON?         │
          │ type in enum? conf ≥ 0.6?  │
          ├── yes → use LLM type ──────┼─ differs? → "needs review"
          └── no  → fallback ──────────┘
                        ▼
         extract_fields(type) regex: notice days, cap months, payer/payee, jurisdiction...
                        ▼
         assess(Policy): perspective-aware flags (HIGH/MEDIUM/LOW) → risk score
```
- **The LLM classifies, and code extracts numbers.** Classification is where language variety matters ("Indemnity" vs "Hold harmless"). Numeric terms like "one hundred twenty (120) days" are parsed by regex, so they can be audited and are never hallucinated.
- **Strict output contract.** Model output must be a JSON object with a known `type` and a confidence in [0, 1]. Anything else (prose, an invented clause type, an out-of-range confidence) falls back to rules and is reported, so you can see how often the model goes off-contract.
- **Disagreement is a signal.** When the LLM and the rules disagree, the clause is routed to human review instead of either one silently winning.
- **Risk is judged from our side of the table.** The same "net 90" term is good when we pay and bad when we're waiting to be paid. The same is true of uncapped liability and one-way indemnities.

## Run
```bash
pip install pytest
python -m pytest -q                                # 15 tests, offline
python -m clause_extractor                         # mock LLM (clause 7 simulates bad output)
ANTHROPIC_API_KEY=... python -m clause_extractor path/to/contracts/
```

## Next steps
- Add clause-level citations (character offsets) so reviewers can jump to the source text.
- Learn the policy thresholds from past legal escalations instead of hard-coding them.
- Generate suggested redlines for HIGH flags from a clause library of pre-approved fallback language.
