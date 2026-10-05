import assert from "node:assert/strict";
import { test } from "node:test";
import { type Feature, rank } from "./rice.ts";
import { planRoadmap } from "./roadmap.ts";

const f = (id: string, reach: number, effort: number, dependsOn?: string[]): Feature =>
  ({ id, name: id, reach, impact: 1, confidence: 1, effort, dependsOn });

test("fills quarters in RICE order within capacity", () => {
  const plan = planRoadmap(rank([f("a", 900, 3), f("b", 600, 2), f("c", 300, 3), f("d", 100, 1)]), 5, 2);
  const q = (id: string) => plan.slots.find((s) => s.feature.id === id)?.quarter;
  assert.equal(q("a"), 1);
  assert.equal(q("b"), 1);
  assert.equal(q("c"), 2);
  assert.equal(q("d"), 2);
  assert.deepEqual(plan.unscheduled, []);
});

test("a dependent never lands before its dependency, even with a higher score", () => {
  const plan = planRoadmap(rank([f("child", 5000, 1, ["parent"]), f("filler", 3000, 4), f("parent", 100, 2)]), 4, 3);
  const q = (id: string) => plan.slots.find((s) => s.feature.id === id)!.quarter;
  assert.ok(q("child") >= q("parent"));
});

test("oversized items and blocked dependencies are reported with a reason", () => {
  const plan = planRoadmap(rank([f("huge", 1000, 9), f("orphan", 500, 1, ["huge"])]), 6, 2);
  const reasons = Object.fromEntries(plan.unscheduled.map((u) => [u.feature.id, u.reason]));
  assert.equal(reasons.huge, "larger than one quarter's capacity");
  assert.equal(reasons.orphan, "waiting on huge");
});
