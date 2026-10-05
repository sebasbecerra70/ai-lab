import assert from "node:assert/strict";
import { test } from "node:test";
import { EpsilonGreedy, ExploreThenCommit, Thompson, UCB1 } from "./bandits.ts";
import { Rng } from "./rng.ts";

test("A/B test splits evenly for its sample, then commits to the observed winner", () => {
  const ab = new ExploreThenCommit(3, 2);
  const first = Array.from({ length: 6 }, () => ab.select());
  assert.deepEqual(first, [0, 1, 2, 0, 1, 2]);
  [0, 1, 2, 0, 1, 2].forEach((arm) => ab.update(arm, arm === 1 ? 1 : 0));
  assert.deepEqual(Array.from({ length: 5 }, () => ab.select()), [1, 1, 1, 1, 1]);
});

test("epsilon-greedy tries every arm once, then epsilon 0 always exploits", () => {
  const g = new EpsilonGreedy(3, 0, new Rng(1));
  for (let a = 0; a < 3; a++) {
    assert.equal(g.select(), a);
    g.update(a, a === 2 ? 1 : 0);
  }
  assert.ok(Array.from({ length: 50 }, () => g.select()).every((a) => a === 2));
  const explorer = new EpsilonGreedy(3, 1, new Rng(2));
  [0, 1, 2].forEach((a) => explorer.update(a, 0));
  assert.equal(new Set(Array.from({ length: 100 }, () => explorer.select())).size, 3);
});

test("UCB1 index is mean plus a bonus that shrinks with pulls", () => {
  const u = new UCB1(2);
  assert.equal(u.select(), 0);
  u.update(0, 1);
  assert.equal(u.select(), 1);
  u.update(1, 0);
  for (let i = 0; i < 98; i++) u.update(1, i % 2);
  u.select(); // t = 3
  assert.equal(u.index(0), 1 + Math.sqrt(2 * Math.log(3)));
  assert.ok(Math.abs(u.index(1) - (49 / 99 + Math.sqrt((2 * Math.log(3)) / 99))) < 1e-12);
  // an arm with one lucky pull still beats a well-measured 49% arm on optimism
  assert.equal(u.select(), 0);
});

test("Thompson sends traffic to the arm the posterior favors and reports P(best)", () => {
  const t = new Thompson(2, new Rng(3));
  for (let i = 0; i < 1000; i++) {
    t.update(0, i < 50 ? 1 : 0); // 5%
    t.update(1, i < 80 ? 1 : 0); // 8%
  }
  const picks = Array.from({ length: 500 }, () => t.select());
  assert.ok(picks.filter((a) => a === 1).length > 480);
  const pb = t.probBest();
  assert.ok(pb[1] > 0.99 && Math.abs(pb[0] + pb[1] - 1) < 1e-9);
});
