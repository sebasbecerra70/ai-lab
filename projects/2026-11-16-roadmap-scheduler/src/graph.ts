// Dependency graph: validation, topological order (Kahn) and cycle reporting.

export interface Epic {
  id: string;
  name: string;
  team: string;
  weeks: number;
  people: number;
  deps: string[];
  value: number;
}

export interface Roadmap {
  targetWeek: number;
  teams: Record<string, number>;
  epics: Epic[];
}

export class RoadmapError extends Error {}

export function validate(r: Roadmap): void {
  const ids = new Set<string>();
  for (const e of r.epics) {
    if (ids.has(e.id)) throw new RoadmapError(`duplicate epic id ${e.id}`);
    ids.add(e.id);
  }
  for (const e of r.epics) {
    for (const d of e.deps) if (!ids.has(d)) throw new RoadmapError(`${e.id} depends on unknown epic ${d}`);
    const cap = r.teams[e.team];
    if (cap === undefined) throw new RoadmapError(`${e.id} assigned to unknown team ${e.team}`);
    if (e.people > cap) throw new RoadmapError(`${e.id} needs ${e.people} people but ${e.team} has ${cap}`);
    if (e.weeks <= 0 || e.people <= 0) throw new RoadmapError(`${e.id} needs positive weeks and people`);
  }
}

/** Kahn's algorithm; ties broken by input order so output is stable. Throws with the cycle path. */
export function topoOrder(epics: Epic[]): Epic[] {
  const indeg = new Map(epics.map((e) => [e.id, e.deps.length]));
  const children = new Map<string, string[]>(epics.map((e) => [e.id, []]));
  for (const e of epics) for (const d of e.deps) children.get(d)!.push(e.id);
  const byId = new Map(epics.map((e) => [e.id, e]));
  const queue = epics.filter((e) => e.deps.length === 0).map((e) => e.id);
  const out: Epic[] = [];
  while (queue.length) {
    const id = queue.shift()!;
    out.push(byId.get(id)!);
    for (const c of children.get(id)!) {
      indeg.set(c, indeg.get(c)! - 1);
      if (indeg.get(c) === 0) queue.push(c);
    }
  }
  if (out.length < epics.length) throw new RoadmapError(`dependency cycle: ${findCycle(epics).join(" -> ")}`);
  return out;
}

function findCycle(epics: Epic[]): string[] {
  const byId = new Map(epics.map((e) => [e.id, e]));
  const state = new Map<string, 1 | 2>(); // 1 = on stack, 2 = done
  const stack: string[] = [];
  const dfs = (id: string): string[] | null => {
    state.set(id, 1);
    stack.push(id);
    for (const d of byId.get(id)!.deps) {
      if (state.get(d) === 1) return [...stack.slice(stack.indexOf(d)), d];
      if (!state.has(d)) {
        const c = dfs(d);
        if (c) return c;
      }
    }
    stack.pop();
    state.set(id, 2);
    return null;
  };
  for (const e of epics) {
    if (!state.has(e.id)) {
      const c = dfs(e.id);
      if (c) return c.reverse(); // deps point backwards; reverse to read in build order
    }
  }
  return [];
}
