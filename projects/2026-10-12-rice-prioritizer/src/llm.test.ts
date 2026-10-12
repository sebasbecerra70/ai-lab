import assert from "node:assert/strict";
import { test } from "node:test";
import { type LLMClient, RATIONALE_SYSTEM, TemplateLLM, writeRationale } from "./llm.ts";

const item = { id: "sso", name: "SAML SSO", quarter: 2, score: 960, rank: 4, pTopN: 0.49, verdict: "contested", notes: "Deal blocker" };

test("template rationale cites numbers and flags contested items", async () => {
  const text = await writeRationale(new TemplateLLM(), [item]);
  assert.match(text, /Q2 SAML SSO: RICE 960 \(#4\); Deal blocker/);
  assert.match(text, /49% of simulations/);
});

test("the LLM gets the strict system prompt and JSON facts", async () => {
  let seen = { system: "", prompt: "" };
  const spy: LLMClient = { complete: async (system, prompt) => { seen = { system, prompt }; return "ok"; } };
  await writeRationale(spy, [item]);
  assert.equal(seen.system, RATIONALE_SYSTEM);
  assert.ok(seen.prompt.includes('"pTopN": 0.49'));
});
