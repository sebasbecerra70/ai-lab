import assert from "node:assert/strict";
import { test } from "node:test";
import type { Feature } from "./rice.ts";
import { monteCarlo, mulberry32, oneAtATime } from "./sensitivity.ts";

const f = (id: string, reach: number, confidence = 1, effort = 1): Feature => ({ id, name: id, reach, impact: 1, confidence, effort });

test("seeded PRNG is reproducible and in [0, 1)", () => {
  const a = mulberry32(7), b = mulberry32(7);
  const xs = Array.from({ length: 100 }, () => a());
  assert.deepEqual(xs, Array.from({ length: 100 }, () => b()));
  assert.ok(xs.every((x) => x >= 0 && x < 1));
});

test("a dominant feature is robust; near-ties are contested", () => {
  const odds = monteCarlo([f("big", 10000), f("x", 1000), f("y", 1010), f("z", 10)], 2, 1000, 1);
  const by = new Map(odds.map((o) => [o.id, o]));
  assert.equal(by.get("big")!.verdict, "robust in");
  assert.equal(by.get("z")!.verdict, "robust out");
  assert.equal(by.get("x")!.verdict, "contested");
  assert.equal(by.get("y")!.verdict, "contested");
});

test("low confidence widens the spread of simulated ranks", () => {
  const field = [600, 700, 800, 900, 1100, 1200, 1300, 1400].map((r, i) => f(`x${i}`, r));
  const spread = (a: Feature) => {
    const o = monteCarlo([a, ...field], 3, 2000, 3).find((x) => x.id === "a")!;
    return o.p90Rank - o.p10Rank;
  };
  // Same RICE score (2000 × 0.5 = 1000 × 1.0), but the low-confidence estimate should spread wider.
  assert.ok(spread(f("a", 2000, 0.5)) > spread(f("a", 1000, 1)));
});

test("one-at-a-time swing flags close competitors only", () => {
  const swings = oneAtATime([f("a", 1000), f("b", 950), f("far", 10)], 0.3);
  const worst = (id: string) => Math.max(...swings.filter((s) => s.id === id).map((s) => s.worstRankChange));
  assert.equal(worst("a"), 1);
  assert.equal(worst("far"), 0);
});
