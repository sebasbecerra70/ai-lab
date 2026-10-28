import assert from "node:assert/strict";
import { test } from "node:test";
import { fitElasticity, optimalPrice, whatIf } from "./elasticity.ts";

const curve = (e: number, prices: number[]) => prices.map((price) => ({ price, units: 1000 * (price / 50) ** e }));

test("log-log fit recovers a known constant elasticity exactly", () => {
  const fit = fitElasticity(curve(-1.8, [40, 45, 50, 55, 60]));
  assert.ok(Math.abs(fit.elasticity + 1.8) < 1e-9);
  assert.ok(Math.abs(fit.r2 - 1) < 1e-9);
  assert.equal(fit.n, 5);
});

test("fit rejects too few points, constant prices and ignores non-positive rows", () => {
  assert.throws(() => fitElasticity([{ price: 10, units: 5 }, { price: 11, units: 4 }]), /at least 3/);
  assert.throws(() => fitElasticity([{ price: 10, units: 5 }, { price: 10, units: 6 }, { price: 10, units: 4 }]), /not identifiable/);
  const fit = fitElasticity([...curve(-1.2, [40, 50, 60]), { price: 0, units: 900 }, { price: 45, units: 0 }]);
  assert.equal(fit.n, 3);
});

test("what-if is anchored at today: 0% change reproduces current revenue and profit", () => {
  const [base] = whatIf(50, 30, 1000, -2, [0]);
  assert.equal(base.units, 1000);
  assert.equal(base.revenue, 50_000);
  assert.equal(base.grossProfit, 20_000);
  assert.equal(base.profitDeltaPct, 0);
});

test("elastic demand loses revenue on a price rise, inelastic demand gains it", () => {
  const [elastic] = whatIf(50, 30, 1000, -2.5, [10]);
  const [inelastic] = whatIf(50, 30, 1000, -0.4, [10]);
  assert.ok(elastic.revenue < 50_000);
  assert.ok(inelastic.revenue > 50_000);
  assert.ok(Math.abs(elastic.units - 1000 * 1.1 ** -2.5) < 1e-9);
});

test("optimal price uses the markup rule c·e/(1+e) and caps outside the observed range", () => {
  // e = -3 -> P* = 1.5 × cost
  assert.deepEqual(optimalPrice(40, -3, 50, 70), { price: 60, bounded: false });
  assert.deepEqual(optimalPrice(40, -3, 50, 55), { price: 55, bounded: true });
  assert.deepEqual(optimalPrice(40, -0.5, 50, 70), { price: 70, bounded: true });
});
