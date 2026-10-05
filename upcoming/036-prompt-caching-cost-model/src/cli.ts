// Demo: npx tsx src/cli.ts [model] [prefixTokens]
import { MODELS } from "./pricing.ts";
import { breakEvenReads, recommend, type Workload } from "./simulate.ts";
import { standardPatterns } from "./traffic.ts";

const model = MODELS[process.argv[2] ?? "claude-sonnet-5-5"];
if (!model) throw new Error(`unknown model; choose one of ${Object.keys(MODELS).join(", ")}`);
const workload: Workload = { prefixTokens: Number(process.argv[3] ?? 12_000), dynamicTokens: 400, outputTokens: 350 };

console.log(`${model.id}: $${model.input}/$${model.output} per MTok, cache read $${model.cacheRead}, min cacheable ${model.minCacheableTokens} tokens`);
console.log(`workload: ${workload.prefixTokens} prefix + ${workload.dynamicTokens} dynamic input, ${workload.outputTokens} output tokens`);
console.log(`break-even: 5m TTL needs ${breakEvenReads(model, "5m")} read per write, 1h TTL needs ${breakEvenReads(model, "1h")}\n`);

const pad = (s: string, n: number) => s.padEnd(n);
const money = (x: number) => `$${x.toFixed(2)}`.padStart(9);
console.log(`${pad("pattern", 15)}${"req/day".padStart(8)}${"no cache".padStart(10)}${"5m".padStart(9)}${"1h".padStart(9)}  hit% 5m/1h   best`);
for (const p of standardPatterns()) {
  const { results: r, best } = recommend(p.arrivals, workload, model);
  const hit = `${(r["5m"].hitRate * 100).toFixed(0)}/${(r["1h"].hitRate * 100).toFixed(0)}`;
  console.log(
    `${pad(p.name, 15)}${String(p.arrivals.length).padStart(8)}${money(r.none.costUsd).padStart(10)}${money(r["5m"].costUsd)}${money(r["1h"].costUsd)}  ${hit.padEnd(11)} ${best.ttl} (-${(best.savingsVsNone * 100).toFixed(0)}%)`,
  );
}
for (const p of standardPatterns()) console.log(`  ${pad(p.name, 15)}${p.description}`);
