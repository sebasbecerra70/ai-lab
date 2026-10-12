// Demo: npm run demo [-- capacity quarters]
import { readFileSync } from "node:fs";
import { AnthropicLLM, type LLMClient, TemplateLLM, writeRationale } from "./llm.ts";
import { type Feature, rank } from "./rice.ts";
import { planRoadmap } from "./roadmap.ts";
import { monteCarlo, oneAtATime } from "./sensitivity.ts";

const features: Feature[] = JSON.parse(readFileSync(new URL("../data/features.json", import.meta.url), "utf8"));
const capacity = Number(process.argv[2] ?? 6);
const quarters = Number(process.argv[3] ?? 2);
const TOP_N = 4;

const ranked = rank(features);
const odds = new Map(monteCarlo(features, TOP_N).map((o) => [o.id, o]));
const swings = oneAtATime(features);

console.log(`RICE ranking (top ${TOP_N} odds from 2000 Monte Carlo runs; reach ±30%, effort ±40%, widened by 1/confidence)`);
console.log("rank  feature                   RICE   P(top4)  rank p10-p90  verdict       most sensitive to");
for (const f of ranked) {
  const o = odds.get(f.id)!;
  const s = swings.filter((x) => x.id === f.id).sort((a, b) => b.worstRankChange - a.worstRankChange)[0];
  console.log(
    `${String(f.rank).padStart(4)}  ${f.name.padEnd(24)}${f.score.toFixed(0).padStart(6)}   ${(o.pTopN * 100).toFixed(0).padStart(5)}%` +
      `   ${`${o.p10Rank}-${o.p90Rank}`.padStart(11)}  ${o.verdict.padEnd(12)}  ${s.factor} (±${s.worstRankChange} ranks)`,
  );
}

const plan = planRoadmap(ranked, capacity, quarters);
console.log(`\nRoadmap: ${quarters} quarters × ${capacity} person-months`);
for (let q = 1; q <= quarters; q++) {
  const items = plan.slots.filter((s) => s.quarter === q);
  const used = items.reduce((t, s) => t + s.feature.effort, 0);
  console.log(`  Q${q} (${used}/${capacity} pm): ${items.map((s) => s.feature.name).join(", ")}`);
}
for (const u of plan.unscheduled) console.log(`  not scheduled: ${u.feature.name} (${u.reason})`);

const llm: LLMClient = process.env.ANTHROPIC_API_KEY ? new AnthropicLLM() : new TemplateLLM();
const rationale = await writeRationale(
  llm,
  plan.slots.map((s) => {
    const o = odds.get(s.feature.id)!;
    return { id: s.feature.id, name: s.feature.name, quarter: s.quarter, score: s.feature.score, rank: s.feature.rank, pTopN: o.pTopN, verdict: o.verdict, notes: s.feature.notes };
  }),
);
console.log(`\nRationale:\n${rationale}`);
