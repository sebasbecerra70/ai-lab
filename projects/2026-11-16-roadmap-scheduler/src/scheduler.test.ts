import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { criticalPath } from "./cpm.ts";
import { type Epic, type Roadmap, RoadmapError, topoOrder, validate } from "./graph.ts";
import { countSuccessors, hiringWhatIf, priorityList, schedule, scheduleWithOrder } from "./schedule.ts";

const roadmap = JSON.parse(readFileSync(new URL("../data/roadmap.json", import.meta.url), "utf8")) as Roadmap;
const epic = (id: string, deps: string[] = [], weeks = 1, team = "t", people = 1): Epic =>
  ({ id, name: id, team, weeks, people, deps, value: 1 });

test("topological order puts every dependency before its dependents", () => {
  const order = topoOrder(roadmap.epics).map((e) => e.id);
  for (const e of roadmap.epics) for (const d of e.deps) assert.ok(order.indexOf(d) < order.indexOf(e.id), `${d} before ${e.id}`);
});

test("cycles are reported with the offending path", () => {
  const epics = [epic("A", ["C"]), epic("B", ["A"]), epic("C", ["B"]), epic("D")];
  assert.throws(() => topoOrder(epics), /dependency cycle: A -> B -> C -> A/);
});

test("validation catches unknown deps, unknown teams and over-sized epics", () => {
  const base = { targetWeek: 10, teams: { t: 2 } };
  assert.throws(() => validate({ ...base, epics: [epic("A", ["X"])] }), RoadmapError);
  assert.throws(() => validate({ ...base, epics: [epic("A", [], 1, "nope")] }), /unknown team/);
  assert.throws(() => validate({ ...base, epics: [epic("A", [], 1, "t", 3)] }), /needs 3 people/);
});

test("critical path matches a hand-computed diamond", () => {
  // A(2) -> B(5) -> D(1), A -> C(1) -> D: the path through B is critical, C has 4 weeks of slack
  const cpm = criticalPath([epic("A", [], 2), epic("B", ["A"], 5), epic("C", ["A"], 1), epic("D", ["B", "C"], 1)]);
  assert.equal(cpm.length, 8);
  assert.deepEqual(cpm.criticalPath, ["A", "B", "D"]);
  assert.equal(cpm.rows.get("C")!.slack, 4);
});

test("sample roadmap critical path runs through billing to launch", () => {
  const cpm = criticalPath(roadmap.epics);
  assert.deepEqual(cpm.criticalPath, ["AUTH", "RBAC", "BILLING", "SELFSERVE", "LAUNCH"]);
  assert.equal(cpm.length, 16);
});

test("schedule respects dependencies and never exceeds team capacity", () => {
  const s = schedule(roadmap);
  const end = new Map(s.slots.map((sl) => [sl.epic.id, sl.end]));
  for (const sl of s.slots) for (const d of sl.epic.deps) assert.ok(sl.start >= end.get(d)!, `${sl.epic.id} after ${d}`);
  for (const [team, cap] of Object.entries(roadmap.teams)) {
    for (let w = 0; w < s.makespan; w++) {
      const load = s.slots.filter((sl) => sl.epic.team === team && sl.start <= w && w < sl.end).reduce((a, sl) => a + sl.epic.people, 0);
      assert.ok(load <= cap, `${team} week ${w}: ${load} > ${cap}`);
    }
  }
  assert.ok(s.makespan >= s.cpmLength);
});

test("capacity forces serialization on a one-person team", () => {
  const s = schedule({ targetWeek: 10, teams: { t: 1 }, epics: [epic("A", [], 2), epic("B", [], 3)] });
  assert.equal(s.makespan, 5);
});

test("local search beats the greedy list on the sample and hits the target week", () => {
  const greedy = scheduleWithOrder(roadmap, priorityList(roadmap));
  const improved = schedule(roadmap);
  assert.equal(greedy.late.map((l) => l.epic.id).join(), "LAUNCH");
  assert.equal(improved.late.length, 0);
  assert.ok(improved.makespan < greedy.makespan);
});

test("successor counts are transitive", () => {
  const succ = countSuccessors(roadmap.epics);
  assert.equal(succ.get("AUTH"), 9);
  assert.equal(succ.get("LAUNCH"), 0);
});

test("hiring what-if identifies web as the bottleneck team", () => {
  const [top, ...rest] = hiringWhatIf(roadmap);
  assert.equal(top.team, "web");
  assert.ok(top.saved > 0);
  assert.ok(rest.every((r) => r.saved === 0));
});
