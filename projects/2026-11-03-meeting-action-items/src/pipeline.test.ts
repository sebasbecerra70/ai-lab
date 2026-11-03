import assert from "node:assert/strict";
import { test } from "node:test";
import { toChecklist, toCSV } from "./export.ts";
import { parseNotes } from "./extract.ts";
import { EXTRACT_SYSTEM, type LLMClient, RecordedLLM } from "./llm.ts";
import { buildPrompt, extract, similarity, validate } from "./pipeline.ts";

const m = parseNotes(`# Standup
Date: 2026-03-02
Attendees: Priya Shah, Sam Lee

Priya will fix the dock scanner by Friday.
Decision: pause the night wave.`);
const act = (o: object) => ({ owner: "Priya", task: "Fix the dock scanner", due: "2026-03-06", evidence: "Priya will fix the dock scanner by Friday.", ...o });
const resp = (actions: object[], decisions: object[] = []) => ({ actions, decisions });

test("validation drops ungrounded items and repairs owners and dates", () => {
  const { extraction, warnings } = validate(resp([
    act({}),
    act({ task: "Invented", evidence: "Sam will rebuild the WMS." }),
    act({ owner: "Facilities", due: "2026-02-01" }),
  ], [{ text: "Pause night wave", evidence: "Decision: pause the night wave." }, { text: "x", evidence: "made up" }]), m);
  assert.equal(extraction.actions.length, 2);
  assert.equal(extraction.actions[0].owner, "Priya Shah");
  assert.deepEqual([extraction.actions[1].owner, extraction.actions[1].due], [null, null]);
  assert.equal(extraction.decisions.length, 1);
  assert.equal(warnings.length, 4);
  assert.throws(() => validate({ actions: "nope" }, m), /schema/);
});

test("LLM path: JSON in prose is parsed and the prompt carries the meeting facts", async () => {
  let seen = { system: "", prompt: "" };
  const llm: LLMClient = { complete: async (system, prompt) => { seen = { system, prompt }; return `Here you go:\n${JSON.stringify(resp([act({})]))}`; } };
  const r = await extract(m, llm);
  assert.equal(r.source, "llm");
  assert.equal(seen.system, EXTRACT_SYSTEM);
  assert.equal(seen.prompt, buildPrompt(m));
  assert.match(seen.prompt, /Attendees: Priya Shah, Sam Lee/);
});

test("falls back to regex on an outage or garbage output, and flags LLM misses", async () => {
  const down = await extract(m, new RecordedLLM({}));
  assert.equal(down.source, "regex");
  assert.match(down.warnings[0], /used regex fallback/);
  const garbage = await extract(m, { complete: async () => "I could not find any items." });
  assert.equal(garbage.source, "regex");
  const lazy = await extract(m, { complete: async () => JSON.stringify(resp([])) });
  assert.equal(lazy.source, "llm");
  assert.equal(lazy.possibleMisses[0].task, "Fix the dock scanner");
  assert.ok(similarity("Fix the dock scanner", "fix dock scanner today") > 0.5);
});

test("exports: checklist groups by owner with unassigned last; CSV escapes cells", async () => {
  const r = await extract(m, { complete: async () => JSON.stringify(resp([act({}), act({ owner: null, task: "Order labels, \"thermal\"", due: null })])) });
  const md = toChecklist(r);
  assert.ok(md.indexOf("Priya Shah: Fix") < md.indexOf("UNASSIGNED: Order"));
  assert.match(md, /\(due Fri 06 Mar\)/);
  assert.match(md, /1 item\(s\) need an owner or a date/);
  const csv = toCSV([r]).split("\n");
  assert.equal(csv[0], "meeting,meeting_date,owner,task,due,source");
  assert.equal(csv[2], 'Standup,2026-03-02,,"Order labels, ""thermal""",,llm');
});
