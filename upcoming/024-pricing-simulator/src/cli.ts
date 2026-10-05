// Demo: fit elasticities, run price what-ifs, show deal waterfalls and discount break-even.
import { readFileSync } from "node:fs";
import { fitElasticity, optimalPrice, whatIf, type Observation } from "./elasticity.ts";
import { breakEvenVolumeIncrease, pocketMargin, waterfall, type Deal } from "./waterfall.ts";

interface Product {
  sku: string;
  name: string;
  listPrice: number;
  unitCost: number;
  monthlyUnits: number;
  history: Observation[];
}

const load = <T>(f: string): T => JSON.parse(readFileSync(new URL(`../data/${f}`, import.meta.url), "utf8"));
const products = load<Product[]>("products.json");
const deals = load<Deal[]>("deals.json");
const $ = (x: number, d = 0) => `$${x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
const pct = (x: number) => `${x >= 0 ? "+" : ""}${x.toFixed(1)}%`;

for (const p of products) {
  const fit = fitElasticity(p.history);
  const margin = ((p.listPrice - p.unitCost) / p.listPrice) * 100;
  console.log(`\n${p.sku} ${p.name}`);
  console.log(`  list ${$(p.listPrice, 2)}, cost ${$(p.unitCost, 2)} (margin ${margin.toFixed(0)}%), ${p.monthlyUnits.toLocaleString()} units/mo`);
  console.log(`  elasticity ${fit.elasticity.toFixed(2)} (R² ${fit.r2.toFixed(2)}, ${fit.n} price points) -> ${fit.elasticity < -1 ? "elastic" : "inelastic"}`);
  console.log(`  ${"change".padStart(8)}${"price".padStart(9)}${"units".padStart(8)}${"revenue".padStart(11)}${"gross profit".padStart(14)}${"vs today".padStart(10)}`);
  for (const w of whatIf(p.listPrice, p.unitCost, p.monthlyUnits, fit.elasticity, [-10, -5, 0, 5, 10])) {
    console.log(`  ${pct(w.priceChangePct).padStart(8)}${$(w.price, 2).padStart(9)}${Math.round(w.units).toLocaleString().padStart(8)}` +
      `${$(w.revenue).padStart(11)}${$(w.grossProfit).padStart(14)}${pct(w.profitDeltaPct).padStart(10)}`);
  }
  const prices = p.history.map((h) => h.price);
  const opt = optimalPrice(p.unitCost, fit.elasticity, Math.min(...prices), Math.max(...prices));
  const note = opt.bounded ? " (capped at the observed price range: the model is not trusted beyond it)" : "";
  console.log(`  profit-maximizing price: ${$(opt.price, 2)}${note}`);
}

console.log("\npocket-price waterfalls:");
for (const d of deals) {
  const p = products.find((x) => x.sku === d.sku)!;
  const steps = waterfall(p.listPrice, p.unitCost, d);
  console.log(`\n  ${d.customer} - ${d.units} x ${d.sku}`);
  for (const s of steps) {
    const amt = s.label.startsWith("=") ? "" : s.label === "list price" ? $(s.amount, 2) : `-${$(-s.amount, 2)}`;
    console.log(`    ${s.label.padEnd(24)}${amt.padStart(9)}${$(s.running, 2).padStart(10)}`);
  }
  const pm = pocketMargin(steps);
  console.log(`    pocket margin ${((pm / p.listPrice) * 100).toFixed(1)}% of list vs ${(((p.listPrice - p.unitCost) / p.listPrice) * 100).toFixed(1)}% list margin; ${$(pm * d.units)} per order`);
}

console.log("\ndiscount break-even (extra volume needed to keep gross profit flat):");
console.log(`  ${"discount".padEnd(10)}${[20, 30, 40, 55].map((m) => `margin ${m}%`.padStart(12)).join("")}`);
for (const disc of [5, 10, 15, 20]) {
  const cells = [20, 30, 40, 55].map((m) => {
    const v = breakEvenVolumeIncrease(disc, m);
    return (Number.isFinite(v) ? `+${v.toFixed(0)}%` : "never").padStart(12);
  });
  console.log(`  ${`${disc}%`.padEnd(10)}${cells.join("")}`);
}
