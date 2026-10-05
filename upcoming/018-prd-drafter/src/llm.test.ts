import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { checkPrd } from "./checker.ts";
import { draftPrd, PRD_SYSTEM, TemplateLLM, type LLMClient } from "./llm.ts";

const scripted: Record<string, string[]> = JSON.parse(readFileSync(new URL("../data/answers.json", import.meta.url), "utf8"));
const finalAnswers = Object.fromEntries(Object.entries(scripted).map(([k, v]) => [k, v[v.length - 1]]));

test("system prompt pins sections and forbids invention", () => {
  for (const s of ["Problem", "Non-goals", "Acceptance criteria", "Launch plan"]) assert.ok(PRD_SYSTEM.includes(s));
  assert.match(PRD_SYSTEM, /do not invent/);
});

test("draftPrd sends the answers as JSON to the model", async () => {
  let seen = "";
  const spy: LLMClient = { complete: async (_s, p) => ((seen = p), "# PRD: x") };
  await draftPrd(spy, { title: "Bulk print" });
  assert.deepEqual(JSON.parse(seen.slice(seen.indexOf("{"))), { title: "Bulk print" });
});

test("template draft from the sample interview passes the checker and keeps every number", async () => {
  const prd = await draftPrd(new TemplateLLM(), finalAnswers);
  assert.equal(checkPrd(prd).score, 100);
  for (const n of ["11 min", "140/month", "200 orders", "30 seconds"]) assert.ok(prd.includes(n), n);
});
