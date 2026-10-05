# Structured Output Validator

Make LLM JSON extraction reliable enough to feed an order system. Validate every output against a JSON Schema, fix the harmless slips locally at zero cost, re-ask the model with the exact validation errors, and hand anything still invalid to a human instead of inventing missing facts.

```text
$ npm run demo

6 purchase-order emails, schema: po_number, customer, currency, requested_date, priority, contact_email, lines

strategy                valid  LLM calls
strict parse, 1 try       1/6          6
local repair, 1 try       3/6          6
repair + re-ask x3        5/6         10

per email (repair + re-ask):
e1 VALID  after 1 call(s)
     try 1 local fixes: stripped code fence; $.lines[1].unit_price: "1,850" -> 1850
e2 VALID  after 2 call(s)
     try 1 local fixes: $.priority: "Expedite" -> "expedite"
     try 1 error: $.currency is required
     try 1 error: $.contact is not allowed
e3 VALID  after 1 call(s)
     try 1 local fixes: repaired JSON syntax
e4 VALID  after 2 call(s)
     try 1 error: $.lines[0].sku "SWT480" does not match ^[A-Z]{3}-\d{3,4}$
e5 VALID  after 1 call(s)
e6 FAILED after 3 call(s)
     try 1 error: $.priority is required
     try 1 error: $.requested_date "end of month" is not a valid date
     try 2 error: $.requested_date "end of month" is not a valid date
     try 2 error: $.priority must be one of "standard", "expedite", got "normal"
     try 3 error: $.requested_date "EOM" is not a valid date
     -> sent to order desk with the errors above (missing facts are not invented)
```

## Why it matters
A "95% accurate" extraction prototype breaks in production because the other 5% is malformed: a code fence, a `"1,850"` string where a number belongs, a made-up field, a priority of `"normal"` that the ERP rejects. At 2,000 order emails a day, 5% means 100 manual fixes or 100 bad writes. In the sample, strict parsing accepts only 1 of 6 outputs. Local repair raises that to 3 at no extra cost. Error-guided re-asks reach 5 of 6 for 4 extra calls, about 67% more calls than single-shot. The last email truly has no delivery date, and the loop sends it to the order desk instead of letting the model guess a date. For an order-entry team, that's the difference between automating most of the inbox and building a second inbox of broken records.

## Architecture
```
email ──► buildPrompt(schema, email [, previous output + errors]) ──► LLMClient (Mock | Claude)
                                                                         │ raw text
         ┌───────────────────────────────────────────────────────────────┘
         ▼
  extractJson(): strip prose/fences, fix trailing commas, single quotes, bare keys     (free)
         ▼
  coerce(): schema-guided, meaning-preserving only: "1,850"→1850, "Expedite"→"expedite" (free)
         ▼
  validate(): type, required, enum, pattern, format, min/max, additionalProperties → [{path, message}]
         ├── no errors ──► typed value
         └── errors ──► attempt < max ? re-ask with "$.lines[0].sku does not match ^[A-Z]{3}-\d{3,4}$"
                                     : FAILED → human queue with the full error history
```
- **Repair locally before paying for another call.** Syntax slips and formatting are deterministic to fix. Spending a model call on a trailing comma wastes latency and money.
- **Coercion never makes judgment calls.** `"Expedite"` becomes `"expedite"` because it's an exact case variant. `"normal"` is not converted to `"standard"`, and `2.5` units are not rounded. Those go back to the model or to a human.
- **Errors are written for the model.** Each error is a JSON path plus a specific message, so a retry fixes the actual problem instead of regenerating everything and introducing new mistakes.
- **Bounded retries, then a human.** The prompt says not to invent missing values, and the loop enforces that with a hard limit. A failed result keeps every attempt for audit.
- **Its own small validator.** It covers the schema subset extraction schemas actually use (about 100 lines, no dependencies) and returns error messages designed to be fed back into a prompt.

## Run
```bash
npm test               # 11 tests (node:test via tsx)
npm run demo           # scripted mock reproduces common model failure modes
ANTHROPIC_API_KEY=... npm run demo   # same pipeline against Claude
```

## Next steps
- Use native tool-use / structured-output modes where available, and keep this validator as the contract check either way.
- Add cross-field business rules (line totals vs. stated total, date not in the past) as a second validation layer.
- Track per-field failure rates over time to find which schema fields or prompts need work.
