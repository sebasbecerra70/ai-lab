// Group commits into user-facing sections; everything internal is counted but not shown.
import type { Commit } from "./commits.ts";

export interface Item {
  id: string; // stable id the LLM must preserve, e.g. "N3"
  area: string;
  text: string;
  refs: string[];
  breakingNote?: string;
}

export interface Notes {
  breaking: Item[];
  features: Item[];
  fixes: Item[];
  performance: Item[];
  internal: number; // chore/ci/test/docs/refactor commits hidden from users
  unparsed: Commit[]; // non-conventional commits a human should look at
}

const INTERNAL = new Set(["chore", "ci", "test", "docs", "refactor", "build", "style"]);

export function group(commits: Commit[], areas: Record<string, string>): Notes {
  const notes: Notes = { breaking: [], features: [], fixes: [], performance: [], internal: 0, unparsed: [] };
  let n = 0;
  for (const c of commits) {
    if (c.type === "other") {
      if (!/^Merge /.test(c.subject)) notes.unparsed.push(c);
      continue;
    }
    if (INTERNAL.has(c.type)) {
      notes.internal++;
      continue;
    }
    const item: Item = { id: `N${++n}`, area: areas[c.scope ?? ""] ?? "General", text: c.subject, refs: c.refs, breakingNote: c.breakingNote };
    if (c.breaking) notes.breaking.push(item);
    else if (c.type === "feat") notes.features.push(item);
    else if (c.type === "fix") notes.fixes.push(item);
    else if (c.type === "perf") notes.performance.push(item);
  }
  return notes;
}

export const allItems = (n: Notes): Item[] => [...n.breaking, ...n.features, ...n.fixes, ...n.performance];

export function render(version: string, notes: Notes, text: Record<string, string> = {}): string {
  const line = (i: Item) => `- **${i.area}:** ${text[i.id] ?? i.text}${i.refs.length ? ` (${i.refs.join(", ")})` : ""}`;
  const out = [`## ${version}`];
  const section = (title: string, items: Item[], extra?: (i: Item) => string) => {
    if (!items.length) return;
    out.push("", `### ${title}`);
    for (const i of items) out.push(line(i) + (extra ? extra(i) : ""));
  };
  section("Breaking changes", notes.breaking, (i) => (i.breakingNote ? `\n  - Action needed: ${i.breakingNote}` : ""));
  section("New", notes.features);
  section("Fixed", notes.fixes);
  section("Faster", notes.performance);
  return out.join("\n");
}
