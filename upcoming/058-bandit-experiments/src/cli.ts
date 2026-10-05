// Demo: npx tsx src/cli.ts [runs]
import { readFileSync } from "node:fs";
import { Thompson } from "./bandits.ts";
import { Rng } from "./rng.ts";
import { bestArm, compare, defaultFactories, runOnce, sampleSizePerArm, type Scenario } from "./simulate.ts";

const scenarios: Scenario[] = JSON.parse(readFileSync(new URL("../data/scenarios.json", import.meta.url), "utf8"));
const runs = Number(process.argv[2] ?? 200);
const pct = (x: number) => `${(100 * x).toFixed(0)}%`;

for (const s of scenarios) {
  const best = s.arms[bestArm(s)];
  const need = sampleSizePerArm(s.arms[0].rate, 0.1);
  console.log(`== ${s.name}: ${s.arms.length} arms, ${s.visitors.toLocaleString("en-US")} visitors, best ${best.id} ` +
    `at ${(100 * best.rate).toFixed(1)}% (${s.note})`);
  console.log(`   a powered A/B test for a 10% lift needs ${need.toLocaleString("en-US")}/arm` +
    (need * s.arms.length > s.visitors ? " - more traffic than the experiment has, so it runs underpowered on half" : ""));
  const res = compare(s, defaultFactories(s), runs);
  const quarter = s.visitors / 4;
  console.log(`   ${"policy".padEnd(24)}${"lost conv".padStart(10)}${"p90".padStart(7)}${"to best".padStart(9)}` +
    `${"picks best".padStart(12)}   regret at ${[1, 2, 3, 4].map((i) => `${(i * quarter) / 1000}k`).join(" / ")}`);
  for (const r of res) {
    console.log(`   ${r.policy.padEnd(24)}${r.meanRegret.toFixed(0).padStart(10)}${r.p90Regret.toFixed(0).padStart(7)}` +
      `${pct(r.bestShare).padStart(9)}${pct(r.pickedBest).padStart(12)}   ${r.regretCurve.map((x) => x.toFixed(0)).join(" / ")}`);
  }
  console.log();
}

// What a Thompson dashboard shows as one experiment unfolds. Same seeds each time, so each snapshot is a
// prefix of the same run.
const s = scenarios[0];
console.log(`${s.name}, one Thompson run: traffic share and posterior P(best) per arm`);
console.log(`   ${"visitors".padEnd(10)}${s.arms.map((a) => a.id.padStart(15)).join("")}`);
for (const seen of [2000, 5000, 10000, 20000]) {
  const ts = new Thompson(s.arms.length, new Rng(42));
  runOnce({ ...s, visitors: seen }, ts, new Rng(43), []);
  const pb = ts.probBest();
  const cells = s.arms.map((_, i) => `${pct(ts.pulls[i] / seen)} / ${pct(pb[i])}`.padStart(15));
  console.log(`   ${seen.toLocaleString("en-US").padEnd(10)}${cells.join("")}`);
}
console.log(`(${runs} simulated experiments per policy; lost conv = expected conversions lost vs always showing the best arm)`);
