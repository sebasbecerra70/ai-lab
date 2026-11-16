// Critical path method on the unconstrained graph (infinite capacity): the best case for the plan.
import { type Epic, topoOrder } from "./graph.ts";

export interface CpmRow {
  id: string;
  es: number; // earliest start week
  ef: number; // earliest finish
  ls: number; // latest start without delaying the project
  lf: number;
  slack: number;
}

export interface CpmResult {
  rows: Map<string, CpmRow>;
  length: number;
  criticalPath: string[];
}

export function criticalPath(epics: Epic[]): CpmResult {
  const order = topoOrder(epics);
  const rows = new Map<string, CpmRow>();
  for (const e of order) {
    const es = Math.max(0, ...e.deps.map((d) => rows.get(d)!.ef));
    rows.set(e.id, { id: e.id, es, ef: es + e.weeks, ls: 0, lf: 0, slack: 0 });
  }
  const length = Math.max(...[...rows.values()].map((r) => r.ef));
  const children = new Map<string, string[]>(epics.map((e) => [e.id, []]));
  for (const e of epics) for (const d of e.deps) children.get(d)!.push(e.id);
  for (const e of [...order].reverse()) {
    const r = rows.get(e.id)!;
    r.lf = Math.min(length, ...children.get(e.id)!.map((c) => rows.get(c)!.ls));
    r.ls = r.lf - e.weeks;
    r.slack = r.ls - r.es;
  }
  // Walk zero-slack epics from a zero-slack root, always following a zero-slack child that starts when we end.
  const path: string[] = [];
  let cur = order.find((e) => rows.get(e.id)!.slack === 0 && rows.get(e.id)!.es === 0);
  while (cur) {
    path.push(cur.id);
    const ef = rows.get(cur.id)!.ef;
    const next = children.get(cur.id)!.find((c) => rows.get(c)!.slack === 0 && rows.get(c)!.es === ef);
    cur = next ? order.find((e) => e.id === next) : undefined;
  }
  return { rows, length, criticalPath: path };
}
