// Demo: extract actions and decisions from every notes file, print checklists (or CSV with --csv).
import { readdirSync, readFileSync } from "node:fs";
import { toChecklist, toCSV } from "./export.ts";
import { parseNotes } from "./extract.ts";
import { AnthropicLLM, type LLMClient, RecordedLLM } from "./llm.ts";
import { extract } from "./pipeline.ts";

const dir = new URL("../data/", import.meta.url);
const recordings: Record<string, string> = Object.fromEntries(
  readdirSync(new URL("recorded/", dir)).map((f) => {
    const r = JSON.parse(readFileSync(new URL(`recorded/${f}`, dir), "utf8"));
    return [r.meeting, JSON.stringify(r.response)];
  }),
);
const llm: LLMClient = process.env.ANTHROPIC_API_KEY ? new AnthropicLLM() : new RecordedLLM(recordings);

const results = [];
for (const f of readdirSync(new URL("notes/", dir)).filter((n) => n.endsWith(".md")).sort()) {
  results.push(await extract(parseNotes(readFileSync(new URL(`notes/${f}`, dir), "utf8")), llm));
}
if (process.argv.includes("--csv")) {
  console.log(toCSV(results));
} else {
  console.log(`LLM: ${llm.constructor.name}\n`);
  console.log(results.map(toChecklist).join("\n\n"));
}
