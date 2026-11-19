import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { type LLMClient, MockLLM } from "./llm.ts";
import { buildPrompt, check, generateValidated } from "./loop.ts";
import { coerce, extractJson } from "./repair.ts";
import { type Schema, validate } from "./schema.ts";

const schema = JSON.parse(readFileSync(new URL("../data/po_schema.json", import.meta.url), "utf8")) as Schema;
const good = {
  po_number: "PO-12345", customer: "Acme", currency: "USD", requested_date: "2026-11-01", priority: "standard",
  lines: [{ sku: "CAB-210", qty: 2, unit_price: 9.5 }],
};

test("a conforming object has no errors", () => {
  assert.deepEqual(validate(good, schema), []);
});

test("errors carry precise paths for nested problems", () => {
  const bad = { ...good, lines: [{ sku: "cab210", qty: 0, unit_price: -1, color: "red" }] };
  const msgs = validate(bad, schema).map((e) => `${e.path} ${e.message}`);
  assert.ok(msgs.some((m) => m.startsWith("$.lines[0].sku") && m.includes("does not match")));
  assert.ok(msgs.includes("$.lines[0].qty 0 is below minimum 1"));
  assert.ok(msgs.includes("$.lines[0].unit_price -1 is below minimum 0"));
  assert.ok(msgs.includes("$.lines[0].color is not allowed"));
});

test("type, enum, required, integer and format checks", () => {
  const { priority: _, ...noPriority } = good;
  assert.deepEqual(validate(noPriority, schema).map((e) => e.path), ["$.priority"]);
  assert.match(validate({ ...good, currency: "JPY" }, schema)[0].message, /must be one of/);
  assert.match(validate({ ...good, requested_date: "2026-02-30" }, schema)[0].message, /not a valid date/);
  assert.match(validate({ ...good, lines: [{ ...good.lines[0], qty: 1.5 }] }, schema)[0].message, /expected integer, got number/);
  assert.match(validate({ ...good, contact_email: "nobody" }, schema)[0].message, /not a valid email/);
});

test("extractJson strips prose and fences and repairs common syntax slips", () => {
  assert.deepEqual(extractJson('Sure! ```json\n{"a": 1}\n``` hope that helps').value, { a: 1 });
  const r = extractJson("{'a': 'x', b: [1, 2,],}");
  assert.deepEqual(r.value, { a: "x", b: [1, 2] });
  assert.ok(r.fixes.includes("repaired JSON syntax"));
  assert.equal(extractJson("I could not find an order.").error, "no JSON object found");
});

test("coerce only applies meaning-preserving fixes", () => {
  const fixes: string[] = [];
  const out = coerce({ ...good, priority: "Expedite", lines: [{ sku: "CAB-210", qty: "40", unit_price: "$1,850.00" }] }, schema, "$", fixes) as typeof good;
  assert.equal(out.priority, "expedite");
  assert.deepEqual(out.lines[0], { sku: "CAB-210", qty: 40, unit_price: 1850 });
  assert.equal(fixes.length, 3);
  // "normal" is not a case variant of an allowed value, so it is left for the model to fix
  assert.equal((coerce({ priority: "normal" }, schema) as { priority: string }).priority, "normal");
  // a fractional quantity is not silently rounded
  assert.equal((coerce("2.5", { type: "integer" }) as string), "2.5");
});

test("strict mode rejects output that local repair accepts", () => {
  const raw = "```json\n" + JSON.stringify(good) + "\n```";
  assert.equal(check(raw, schema, false).errors.length, 1);
  assert.equal(check(raw, schema, true).errors.length, 0);
});

test("retry prompt includes the previous output and the exact errors", () => {
  const p = buildPrompt("e9", "email", schema, 2, { raw: '{"x":1}', localFixes: [], errors: [{ path: "$.currency", message: "is required" }] });
  assert.match(p, /ATTEMPT: 2/);
  assert.match(p, /YOUR PREVIOUS OUTPUT:\n\{"x":1\}/);
  assert.match(p, /- \$\.currency is required/);
  assert.match(p, /do not invent/);
});

test("the loop re-asks until valid and stops as soon as it is", async () => {
  const llm = new MockLLM();
  const r = await generateValidated(llm, schema, "e2", "...");
  assert.ok(r.ok);
  assert.equal(r.llmCalls, 2);
  assert.equal(llm.calls, 2);
  assert.equal((r.value as { currency: string }).currency, "USD");
});

test("the loop gives up after maxAttempts and keeps every error for a human", async () => {
  const r = await generateValidated(new MockLLM(), schema, "e6", "...", { maxAttempts: 3 });
  assert.equal(r.ok, false);
  assert.equal(r.attempts.length, 3);
  assert.ok(r.attempts.every((a) => a.errors.some((e) => e.path === "$.requested_date")));
});

test("repair + re-ask beats strict parsing on the sample emails", async () => {
  const emails = JSON.parse(readFileSync(new URL("../data/emails.json", import.meta.url), "utf8")) as { id: string; text: string }[];
  const run = async (opts: object) => {
    let ok = 0;
    for (const e of emails) ok += Number((await generateValidated(new MockLLM(), schema, e.id, e.text, opts)).ok);
    return ok;
  };
  assert.equal(await run({ maxAttempts: 1, localRepair: false }), 1);
  assert.equal(await run({ maxAttempts: 1 }), 3);
  assert.equal(await run({ maxAttempts: 3 }), 5);
});

test("a model that never returns JSON fails cleanly", async () => {
  const chatty: LLMClient = { complete: async () => "Happy to help with your order!" };
  const r = await generateValidated(chatty, schema, "x", "...", { maxAttempts: 2 });
  assert.equal(r.ok, false);
  assert.equal(r.attempts[1].errors[0].message, "no JSON object found");
});
