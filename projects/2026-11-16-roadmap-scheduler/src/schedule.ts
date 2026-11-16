// Resource-constrained scheduling: serial list scheduling with a priority rule, then local search on the list.
import { criticalPath } from "./cpm.ts";
import { type Epic, type Roadmap, validate } from "./graph.ts";

export interface Slot {
  epic: Epic;
  start: number;
  end: number;
  delay: number; // weeks later than the unconstrained earliest start, caused by team capacity
}

export interface Schedule {
  slots: Slot[];
  makespan: number;
  cpmLength: number;
  utilization: Record<string, number>; // busy person-weeks / available person-weeks up to makespan
  late: Slot[]; // epics finishing after the target week
  order: string[]; // the priority list that produced this schedule
}

/** Initial priority list: least latest-start (most urgent), then most downstream epics, then highest value. */
export function priorityList(r: Roadmap): string[] {
  const cpm = criticalPath(r.epics);
  const succ = countSuccessors(r.epics);
  return [...r.epics]
    .sort((a, b) => cpm.rows.get(a.id)!.ls - cpm.rows.get(b.id)!.ls || succ.get(b.id)! - succ.get(a.id)! || b.value - a.value)
    .map((e) => e.id);
}

/** Serial schedule generation: repeatedly take the first epic in `order` whose deps are scheduled,
 *  and place it at the earliest week where its team has enough free people for its whole duration. */
export function scheduleWithOrder(r: Roadmap, order: string[]): Schedule {
  validate(r);
  const cpm = criticalPath(r.epics);
  const byId = new Map(r.epics.map((e) => [e.id, e]));
  const usage = new Map<string, number[]>(Object.keys(r.teams).map((t) => [t, []]));
  const done = new Map<string, Slot>();
  const pending = [...order];

  while (pending.length) {
    const idx = pending.findIndex((id) => byId.get(id)!.deps.every((d) => done.has(d)));
    const e = byId.get(pending.splice(idx, 1)[0])!;
    const ready = Math.max(0, ...e.deps.map((d) => done.get(d)!.end));
    const used = usage.get(e.team)!;
    let start = ready;
    while (!fits(used, start, e.weeks, e.people, r.teams[e.team])) start++;
    for (let w = start; w < start + e.weeks; w++) used[w] = (used[w] ?? 0) + e.people;
    done.set(e.id, { epic: e, start, end: start + e.weeks, delay: start - cpm.rows.get(e.id)!.es });
  }

  const slots = r.epics.map((e) => done.get(e.id)!).sort((a, b) => a.start - b.start || a.end - b.end);
  const makespan = Math.max(...slots.map((s) => s.end));
  const utilization: Record<string, number> = {};
  for (const [team, cap] of Object.entries(r.teams)) {
    const busy = usage.get(team)!.reduce((a, b) => a + (b ?? 0), 0);
    utilization[team] = busy / (cap * makespan);
  }
  return { slots, makespan, cpmLength: cpm.length, utilization, late: slots.filter((s) => s.end > r.targetWeek), order };
}

/** Lexicographic objective: fewest late epics, then shortest plan, then high-value epics shipped early. */
export function cost(s: Schedule): [number, number, number] {
  return [s.late.length, s.makespan, s.slots.reduce((a, sl) => a + sl.epic.value * sl.end, 0)];
}

const better = (a: [number, number, number], b: [number, number, number]) =>
  a[0] - b[0] || a[1] - b[1] || a[2] - b[2];

/** Greedy list + hill climbing: try moving each epic earlier in the list; keep any move that lowers cost. */
export function schedule(r: Roadmap, maxPasses = 20): Schedule {
  let best = scheduleWithOrder(r, priorityList(r));
  for (let pass = 0; pass < maxPasses; pass++) {
    let improved = false;
    for (let i = 1; i < best.order.length; i++) {
      for (let j = 0; j < i; j++) {
        const order = [...best.order];
        order.splice(j, 0, order.splice(i, 1)[0]);
        const cand = scheduleWithOrder(r, order);
        if (better(cost(cand), cost(best)) < 0) {
          best = cand;
          improved = true;
        }
      }
    }
    if (!improved) break;
  }
  return best;
}

/** Number of epics transitively blocked by each epic. */
export function countSuccessors(epics: Epic[]): Map<string, number> {
  const children = new Map<string, string[]>(epics.map((e) => [e.id, []]));
  for (const e of epics) for (const d of e.deps) children.get(d)!.push(e.id);
  const reach = (id: string, seen: Set<string>): Set<string> => {
    for (const c of children.get(id)!) if (!seen.has(c)) reach(c, seen.add(c));
    return seen;
  };
  return new Map(epics.map((e) => [e.id, reach(e.id, new Set()).size]));
}

function fits(used: number[], start: number, weeks: number, people: number, cap: number): boolean {
  for (let w = start; w < start + weeks; w++) if ((used[w] ?? 0) + people > cap) return false;
  return true;
}

/** "What if we hired one more person on team X?" -> weeks saved per team. Finds the bottleneck. */
export function hiringWhatIf(r: Roadmap): { team: string; makespan: number; saved: number }[] {
  const base = schedule(r).makespan;
  return Object.keys(r.teams)
    .map((team) => {
      const m = schedule({ ...r, teams: { ...r.teams, [team]: r.teams[team] + 1 } }).makespan;
      return { team, makespan: m, saved: base - m };
    })
    .sort((a, b) => b.saved - a.saved);
}

export function gantt(s: Schedule, targetWeek: number): string {
  const width = Math.max(s.makespan, targetWeek);
  const header = "".padEnd(10) + Array.from({ length: width }, (_, w) => (w % 5 === 0 ? "|" : " ")).join("") + `  target=w${targetWeek}`;
  const rows = s.slots.map((sl) => {
    const bar = Array.from({ length: width }, (_, w) =>
      w >= sl.start && w < sl.end ? "#" : w === targetWeek - 1 ? ":" : ".",
    ).join("");
    const note = sl.delay > 0 ? `  +${sl.delay}w capacity wait` : "";
    return `${sl.epic.id.padEnd(10)}${bar}  w${sl.start}-w${sl.end} ${sl.epic.team}${note}`;
  });
  return [header, ...rows].join("\n");
}
