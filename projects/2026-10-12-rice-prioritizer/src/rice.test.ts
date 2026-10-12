import assert from "node:assert/strict";
import { test } from "node:test";
import { type Feature, rank, riceScore, validate } from "./rice.ts";

const f = (id: string, reach: number, impact: number, confidence: number, effort: number, dependsOn?: string[]): Feature =>
  ({ id, name: id, reach, impact, confidence, effort, dependsOn });

test("RICE score is reach × impact × confidence ÷ effort", () => {
  assert.equal(riceScore(f("a", 1000, 2, 0.8, 4)), 400);
});

test("rank orders by score with a stable id tie-break", () => {
  const ranked = rank([f("b", 100, 1, 1, 1), f("a", 100, 1, 1, 1), f("c", 500, 1, 1, 1)]);
  assert.deepEqual(ranked.map((r) => [r.id, r.rank]), [["c", 1], ["a", 2], ["b", 3]]);
});

test("validation enforces the standard scales and catches bad references", () => {
  assert.deepEqual(validate(f("ok", 10, 2, 0.8, 1)), []);
  assert.match(validate(f("x", 10, 1.5, 0.8, 1)).join(), /impact must be one of/);
  assert.match(validate(f("x", 10, 1, 1.2, 1)).join(), /confidence/);
  assert.match(validate(f("x", 10, 1, 1, 0)).join(), /effort/);
  assert.throws(() => rank([f("a", 1, 1, 1, 1, ["ghost"])]), /unknown dependency ghost/);
  assert.throws(() => rank([f("a", 1, 1, 1, 1), f("a", 2, 1, 1, 1)]), /duplicate id a/);
});
