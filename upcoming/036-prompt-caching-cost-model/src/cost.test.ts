import assert from "node:assert/strict";
import { test } from "node:test";
import { MODELS, usd } from "./pricing.ts";
import { breakEvenReads, recommend, simulate, type Workload } from "./simulate.ts";
import { mulberry32, poissonArrivals, standardPatterns } from "./traffic.ts";

const sonnet = MODELS["claude-sonnet-5-5"];
const w: Workload = { prefixTokens: 10_000, dynamicTokens: 0, outputTokens: 0 };
const close = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

test("usd converts per-million pricing", () => {
  close(usd(1_000_000, 2), 2);
  close(usd(500, 10), 0.005);
});

test("first request writes, later requests inside the TTL read", () => {
  const r = simulate([0, 60, 120], w, sonnet, "5m");
  assert.equal(r.writes, 1);
  assert.equal(r.hits, 2);
  close(r.inputCostUsd, usd(10_000, 2 * 1.25) + 2 * usd(10_000, 0.2));
});

test("reads refresh the TTL so steady traffic never expires", () => {
  const arrivals = Array.from({ length: 100 }, (_, i) => i * 240); // every 4 minutes
  assert.equal(simulate(arrivals, w, sonnet, "5m").writes, 1);
  assert.equal(simulate([0, 301], w, sonnet, "5m").writes, 2); // gap longer than 5 minutes
});

test("1h TTL survives gaps that kill the 5m cache but pays a 2x write", () => {
  const arrivals = [0, 1200, 2400, 3600];
  const five = simulate(arrivals, w, sonnet, "5m");
  const hour = simulate(arrivals, w, sonnet, "1h");
  assert.equal(five.writes, 4);
  assert.equal(hour.writes, 1);
  assert.ok(hour.costUsd < five.costUsd);
  assert.ok(five.costUsd > simulate(arrivals, w, sonnet, "none").costUsd); // all writes, no reads
});

test("prefixes below the model minimum silently do not cache", () => {
  const small: Workload = { prefixTokens: 3000, dynamicTokens: 100, outputTokens: 100 };
  const haiku = simulate([0, 10, 20], small, MODELS["claude-haiku-4-5"], "5m");
  assert.equal(haiku.cacheable, false);
  assert.equal(haiku.hits, 0);
  assert.equal(simulate([0, 10, 20], small, sonnet, "5m").hits, 2);
});

test("break-even read counts follow the write premiums", () => {
  assert.equal(breakEvenReads(sonnet, "5m"), 1); // 0.25 premium < 0.9 saved per read
  assert.equal(breakEvenReads(sonnet, "1h"), 2); // 1.0 premium needs two reads at 0.9
  assert.equal(breakEvenReads(MODELS["claude-opus-5-5"], "1h"), 2);
});

test("output cost is unaffected by caching", () => {
  const ww: Workload = { prefixTokens: 2000, dynamicTokens: 50, outputTokens: 300 };
  const a = simulate([0, 5, 10], ww, sonnet, "none");
  const b = simulate([0, 5, 10], ww, sonnet, "5m");
  close(a.outputCostUsd, b.outputCostUsd);
  assert.ok(b.inputCostUsd < a.inputCostUsd);
});

test("traffic generator is deterministic and respects the rate", () => {
  assert.equal(mulberry32(7)(), mulberry32(7)());
  const a = poissonArrivals(() => 60, 60, 36_000, 1);
  assert.deepEqual(a, poissonArrivals(() => 60, 60, 36_000, 1));
  assert.ok(a.length > 500 && a.length < 700); // ~600 expected over 10h
  assert.ok(a.every((t, i) => i === 0 || t > a[i - 1]));
});

test("recommendation picks 5m for steady traffic and 1h for sparse traffic", () => {
  const ww: Workload = { prefixTokens: 12_000, dynamicTokens: 400, outputTokens: 350 };
  const byName = Object.fromEntries(standardPatterns().map((p) => [p.name, recommend(p.arrivals, ww, sonnet).best]));
  assert.equal(byName.steady.ttl, "5m");
  assert.equal(byName.sparse.ttl, "1h");
  assert.ok(byName.steady.savingsVsNone > 0.5);
});
