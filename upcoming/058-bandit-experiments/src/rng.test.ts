import assert from "node:assert/strict";
import { test } from "node:test";
import { Rng } from "./rng.ts";

test("same seed gives the same stream, uniform draws stay in [0, 1)", () => {
  const a = new Rng(7);
  const b = new Rng(7);
  const xs = Array.from({ length: 1000 }, () => a.next());
  assert.deepEqual(xs, Array.from({ length: 1000 }, () => b.next()));
  assert.ok(xs.every((x) => x >= 0 && x < 1));
  assert.notDeepEqual(xs.slice(0, 5), Array.from({ length: 5 }, () => new Rng(8).next()));
});

test("beta draws have the right mean and stay in (0, 1)", () => {
  const rng = new Rng(1);
  for (const [a, b] of [[2, 8], [41, 961], [0.5, 0.5]]) {
    const n = 20000;
    const xs = Array.from({ length: n }, () => rng.beta(a, b));
    const mean = xs.reduce((s, x) => s + x, 0) / n;
    assert.ok(Math.abs(mean - a / (a + b)) < 0.01, `Beta(${a},${b}) mean ${mean}`);
    assert.ok(xs.every((x) => x > 0 && x < 1));
  }
});
