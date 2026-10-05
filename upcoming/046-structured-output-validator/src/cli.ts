// Demo: npx tsx src/cli.ts  — extract purchase orders from emails, comparing three validation strategies.
import { readFileSync } from "node:fs";
import { AnthropicLLM, type LLMClient, MockLLM } from "./llm.ts";
import { generateValidated } from "./loop.ts";
import type { Schema } from "./schema.ts";

const schema = JSON.parse(readFileSync(new URL("../data/po_schema.json", import.meta.url), "utf8")) as Schema;
const emails = JSON.parse(readFileSync(new URL("../data/emails.json", import.meta.url), "utf8")) as { id: string; text: string }[];
const live = Boolean(process.env.ANTHROPIC_API_KEY);
const makeLLM = (): LLMClient => (live ? new AnthropicLLM() : new MockLLM());

const strategies = [
  { name: "strict parse, 1 try", opts: { maxAttempts: 1, localRepair: false } },
  { name: "local repair, 1 try", opts: { maxAttempts: 1, localRepair: true } },
  { name: "repair + re-ask x3", opts: { maxAttempts: 3, localRepair: true } },
];

console.log(`${emails.length} purchase-order emails, schema: ${Object.keys(schema.properties!).join(", ")}\n`);
console.log(`${"strategy".padEnd(22)}${"valid".padStart(7)}${"LLM calls".padStart(11)}`);
for (const s of strategies) {
  let ok = 0;
  let calls = 0;
  for (const e of emails) {
    const r = await generateValidated(makeLLM(), schema, e.id, e.text, s.opts);
    ok += Number(r.ok);
    calls += r.llmCalls;
  }
  console.log(`${s.name.padEnd(22)}${`${ok}/${emails.length}`.padStart(7)}${String(calls).padStart(11)}`);
}

console.log("\nper email (repair + re-ask):");
for (const e of emails) {
  const r = await generateValidated(makeLLM(), schema, e.id, e.text);
  console.log(`${e.id} ${r.ok ? "VALID " : "FAILED"} after ${r.llmCalls} call(s)`);
  r.attempts.forEach((a, i) => {
    if (a.localFixes.length) console.log(`     try ${i + 1} local fixes: ${a.localFixes.join("; ")}`);
    for (const err of a.errors) console.log(`     try ${i + 1} error: ${err.path} ${err.message}`);
  });
  if (!r.ok) console.log("     -> sent to order desk with the errors above (missing facts are not invented)");
}
