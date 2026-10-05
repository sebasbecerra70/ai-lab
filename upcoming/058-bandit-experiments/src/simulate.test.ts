import assert from "node:assert/strict";
import { test } from "node:test";
import { type Policy } from "./bandits.ts";
import { Rng } from "./rng.ts";
import { bestArm, compare, defaultFactories, runOnce, sampleSizePerArm, type Scenario } from "./simulate.ts";

const cta: Scenario = {
  name: "cta",
  visitors: 10000,
  arms: [{ id: "a", rate: 0.04 }, { id: "b", rate: 0.06 }, { id: "c", rate: 0.03 }],
};

const fixed = (arm: number): Policy => ({ name: `always ${arm}`, select: () => arm, update: () => {} });

test("sample size matches the textbook formula", () => {
  // 10% baseline, 20% relative lift (10% -> 12%): about 3,841 per arm at alpha 0.05, power 0.8
  assert.equal(sampleSizePerArm(0.1, 0.2), 3841);
  assert.ok(sampleSizePerArm(0.04, 0.1) > sampleSizePerArm(0.04, 0.2) * 3.5);
});

test("regret is zero for the oracle and grows linearly for a bad fixed arm", () => {
  const cps = [2500, 5000, 10000];
  assert.equal(bestArm(cta), 1);
  assert.deepEqual(runOnce(cta, fixed(1), new Rng(1), cps).regret, [0, 0, 0]);
  const bad = runOnce(cta, fixed(2), new Rng(1), cps).regret;
  bad.forEach((r, i) => assert.ok(Math.abs(r - cps[i] * 0.03) < 1e-6));
});

test("cumulative regret never decreases and pulls add up to the visitors", () => {
  const [ab, eps, ucb, ts] = defaultFactories(cta);
  for (const make of [ab, eps, ucb, ts]) {
    const r = runOnce(cta, make(3, new Rng(5)), new Rng(6), [1000, 2000, 5000, 10000]);
    r.regret.slice(1).forEach((x, i) => assert.ok(x >= r.regret[i]));
    assert.equal(r.pulls.reduce((a, b) => a + b, 0), cta.visitors);
  }
});

test("adaptive policies lose fewer conversions than the A/B test, Thompson the fewest", () => {
  const [ab, eps, , ts] = compare(cta, defaultFactories(cta), 40);
  assert.ok(ts.meanRegret < ab.meanRegret * 0.75, `${ts.meanRegret} vs ${ab.meanRegret}`);
  assert.ok(ts.meanRegret <= eps.meanRegret);
  assert.ok(ts.bestShare > ab.bestShare);
  assert.ok(ts.pickedBest >= 0.9);
});

test("comparison is reproducible for a seed", () => {
  const a = compare(cta, defaultFactories(cta), 5, 9);
  const b = compare(cta, defaultFactories(cta), 5, 9);
  assert.deepEqual(a, b);
});
