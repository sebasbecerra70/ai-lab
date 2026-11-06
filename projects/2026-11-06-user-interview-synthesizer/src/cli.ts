// Demo: npx tsx src/cli.ts [path/to/interviews.txt]
import { readFileSync } from "node:fs";
import { buildAffinityMap, renderAffinityMap, tagAll } from "./affinity.ts";
import { summarize } from "./insights.ts";
import { AnthropicLLM, type LLMClient, MockLLM } from "./llm.ts";
import { parseTranscripts } from "./parse.ts";

const path = process.argv[2] ?? new URL("../data/interviews.txt", import.meta.url).pathname;
const { participants, quotes } = parseTranscripts(readFileSync(path, "utf8"));
const tagged = tagAll(quotes);
const { clusters, untagged } = buildAffinityMap(tagged, participants.length);

console.log(`${participants.length} interviews, ${quotes.length} participant quotes, ${untagged.length} untagged\n`);
console.log("AFFINITY MAP (ranked by reach, pain first)");
console.log(renderAffinityMap(clusters));

const llm: LLMClient = process.env.ANTHROPIC_API_KEY ? new AnthropicLLM() : new MockLLM();
const { summary, check } = await summarize(llm, clusters, participants.length);
console.log("\nINSIGHTS");
console.log(summary);
console.log(`\ncitation check: ${check.cited.length} cited, ${check.unknown.length} unknown, ${check.uncitedLines} uncited insight lines`);
