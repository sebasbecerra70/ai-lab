// Demo: npx tsx src/cli.ts [commits.txt] [current-version]
import { readFileSync } from "node:fs";
import { dedupe, nextVersion, parseLog, semverBump } from "./commits.ts";
import { AnthropicLLM, type LLMClient, MockLLM } from "./llm.ts";
import { allItems, group, render } from "./notes.ts";
import { polish } from "./polish.ts";

const path = process.argv[2] ?? new URL("../data/commits.txt", import.meta.url).pathname;
const current = process.argv[3] ?? "3.7.2";
const glossary = JSON.parse(readFileSync(new URL("../data/glossary.json", import.meta.url), "utf8")) as {
  areas: Record<string, string>;
  jargon: Record<string, string>;
};

const parsed = parseLog(readFileSync(path, "utf8"));
const { kept, dropped } = dedupe(parsed);
const notes = group(kept, glossary.areas);
const bump = semverBump(kept);
const version = nextVersion(current, bump);
console.log(`${parsed.length} commits: ${dropped.length} duplicate, ${notes.internal} internal (hidden), ${notes.unparsed.length} non-conventional`);
for (const u of notes.unparsed) console.log(`  needs a human: ${u.hash} "${u.subject}"`);
console.log(`semver: ${current} -> ${version} (${bump}: ${notes.breaking.length} breaking change(s))\n`);

const llm: LLMClient = process.env.ANTHROPIC_API_KEY ? new AnthropicLLM() : new MockLLM();
const items = allItems(notes);
const p = await polish(llm, items, notes, glossary.jargon);
console.log(render(version, notes, p.text));
console.log(`\npolish: ${Object.keys(p.text).length}/${items.length} rewrites accepted`);
for (const r of p.rejected) console.log(`  kept original for ${r.id}: ${r.reason}${r.proposed ? ` ("${r.proposed}")` : ""}`);
