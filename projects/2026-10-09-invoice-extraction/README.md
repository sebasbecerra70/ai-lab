# Invoice Extraction with Guardrails

Turns messy supplier invoice text into **validated, AP-ready JSON**. An LLM extracts fields against a JSON schema. Business rules check every result (totals must reconcile, dates must be valid), and a deterministic regex extractor fills in any field the model got wrong.

```text
$ python -m invoice_extract
acme_freight.txt: AF-20931 ACME FREIGHT LOGISTICS LLC  USD 3420.0  lines=3  [ok]
brightpack.txt: BP-7781 BrightPack Packaging Supplies  USD 1143.12  lines=3  [ok]
delta_parts.txt: DIP-11873 Delta Industrial Parts Inc.  USD 868.8  lines=3  [ok]
    llm issues: {'_': 'unparseable'}
    regex filled: currency, due_date, invoice_date, invoice_number, line_items, po_number, subtotal, tax, total, vendor
nordic_cold.txt: NCC-2026-0412 Nordic Cold Chain AB  EUR 2226.25  lines=2  [ok]
    llm issues: {'total': 'does not equal subtotal + tax'}
    regex filled: total
```

## Why it matters
A mid-size distributor gets roughly 3,000 supplier invoices a month in dozens of layouts. Manual keying costs about $4–8 per invoice and introduces errors. A plain "ask the LLM for JSON" pipeline handles layout variety well, but its failures are silent: a transposed total (2,262.25 instead of 2,226.25) posts to the ledger and gets paid. Here, **no number is accepted unless the invoice reconciles** (line amounts = qty × price, subtotal = sum of lines, total = subtotal + tax), so an error either gets fixed or goes to a human. The demo shows both kinds of recovery: a hallucinated total and a truncated reply.

## Architecture
```
invoice text ─┬─► LLMClient.complete(system + JSON schema) ─► parse_json_object
              │        (fences / preamble tolerant; truncated → None)
              │                         │
              │                    _coerce (date formats)
              │                         │
              │                    validate() ── business rules
              │                         │ failing fields
              └─► regex_extract ────────┴─► field-level merge (regex only where LLM failed)
                                              │
                                         validate() again
                                              │
                               status ok  |  needs_review (+ reasons)
```
- **The LLM is primary and regex is the safety net.** The LLM handles unseen layouts. Regex handles the common ones and never invents a value. Merging per field keeps the LLM's good fields (vendor names, line descriptions) and replaces only the ones that failed.
- **Reconciliation is the strongest check.** Invoices carry their own checksum (lines → subtotal → total). Using it catches most numeric hallucinations without any labeled data.
- **A failing `total` makes `subtotal` and `tax` suspect too**, because the validator can't tell which of the three is wrong. The merge rechecks all three.
- **Recorded responses as the mock.** `RecordedLLM` replays real failure modes (code fences, chatty preamble, US-format date, transposed digits, truncated JSON), so tests exercise the guardrails rather than an ideal model.
- **Trade-off:** regex assumes US date order for `MM/DD/YYYY`. For EU suppliers, use a per-vendor locale profile.

## Run
```bash
pip install pytest
python -m pytest -q                               # 13 tests, offline
python -m invoice_extract                         # all sample invoices
python -m invoice_extract data/invoices/brightpack.txt --json
ANTHROPIC_API_KEY=... python -m invoice_extract   # live extraction with Claude
```

## Next steps
- Three-way match: compare extracted lines against the PO and receiving records.
- Track per-vendor LLM error rates and promote stable vendors to regex-only templates.
- Add PDF-to-text (pdftotext or a vision model) in front of the pipeline.
