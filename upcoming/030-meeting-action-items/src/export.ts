// Exports: a Markdown checklist grouped by owner (for the follow-up email) and CSV (for a tracker import).
import { pretty } from "./dates.ts";
import type { Result } from "./pipeline.ts";

export function toChecklist(r: Result): string {
  const { meeting: m, extraction: x } = r;
  const lines = [`## ${m.title} (${pretty(m.date)}), extracted by ${r.source}`];
  if (x.decisions.length) lines.push("", "Decisions:", ...x.decisions.map((d) => `- ${d.text}`));
  const owners = [...new Set(x.actions.map((a) => a.owner ?? "UNASSIGNED"))].sort((a, b) =>
    a === "UNASSIGNED" ? 1 : b === "UNASSIGNED" ? -1 : a.localeCompare(b));
  lines.push("", "Action items:");
  for (const o of owners) {
    for (const a of x.actions.filter((y) => (y.owner ?? "UNASSIGNED") === o).sort((p, q) => (p.due ?? "9").localeCompare(q.due ?? "9"))) {
      lines.push(`- [ ] ${o}: ${a.task}${a.due ? ` (due ${pretty(a.due)})` : " (no due date)"}`);
    }
  }
  const gaps = x.actions.filter((a) => !a.owner || !a.due).length;
  if (gaps) lines.push(`  ${gaps} item(s) need an owner or a date before this goes out`);
  for (const w of r.warnings) lines.push(`  warning: ${w}`);
  for (const p of r.possibleMisses) lines.push(`  check: regex also found "${p.task}"`);
  return lines.join("\n");
}

const csvCell = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);

export function toCSV(results: Result[]): string {
  const rows = [["meeting", "meeting_date", "owner", "task", "due", "source"]];
  for (const r of results)
    for (const a of r.extraction.actions)
      rows.push([r.meeting.title, r.meeting.date, a.owner ?? "", a.task, a.due ?? "", r.source]);
  return rows.map((row) => row.map(csvCell).join(",")).join("\n");
}
