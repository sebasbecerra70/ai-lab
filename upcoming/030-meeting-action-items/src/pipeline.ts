// LLM first, validated against the notes; regex fallback when the model fails; cross-check for misses.
import { parseISO } from "./dates.ts";
import { type ActionItem, type Extraction, type Meeting, matchAttendee, regexExtract } from "./extract.ts";
import { EXTRACT_SYSTEM, type LLMClient } from "./llm.ts";

export interface Result {
  meeting: Meeting;
  source: "llm" | "regex";
  extraction: Extraction;
  warnings: string[];
  possibleMisses: ActionItem[]; // regex hits the LLM did not return, for a human to glance at
}

export function buildPrompt(m: Meeting): string {
  return `Meeting: ${m.title}\nDate: ${m.date}\nAttendees: ${m.attendees.join(", ")}\n\nNotes:\n${m.body}`;
}

const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ").trim();

/** Keep only what the notes support: verbatim evidence, a real attendee, a due date that parses and isn't in the past. */
export function validate(raw: unknown, m: Meeting): { extraction: Extraction; warnings: string[] } {
  const warnings: string[] = [];
  const obj = raw as Partial<Extraction>;
  if (!obj || !Array.isArray(obj.actions) || !Array.isArray(obj.decisions)) throw new Error("response does not match schema");
  const notes = norm(m.body);
  const grounded = (e: unknown) => typeof e === "string" && e.trim() !== "" && notes.includes(norm(e));
  const actions: ActionItem[] = [];
  for (const a of obj.actions) {
    if (!a || typeof a.task !== "string" || !a.task.trim()) {
      warnings.push("dropped an action with no task");
      continue;
    }
    if (!grounded(a.evidence)) {
      warnings.push(`dropped "${a.task}": evidence not found in the notes`);
      continue;
    }
    let owner = a.owner ? matchAttendee(a.owner, m.attendees) : null;
    if (a.owner && !owner) warnings.push(`"${a.task}": owner "${a.owner}" is not an attendee, left unassigned`);
    let due = a.due ?? null;
    if (due !== null) {
      try {
        if (parseISO(due) < parseISO(m.date)) throw new Error("past");
      } catch {
        warnings.push(`"${a.task}": due "${due}" is invalid or before the meeting, cleared`);
        due = null;
      }
    }
    actions.push({ owner, task: a.task.trim(), due, evidence: a.evidence });
  }
  const decisions = obj.decisions.filter((d) => d && typeof d.text === "string" && grounded(d.evidence));
  if (decisions.length < obj.decisions.length) warnings.push(`dropped ${obj.decisions.length - decisions.length} ungrounded decision(s)`);
  return { extraction: { actions, decisions }, warnings };
}

const words = (s: string) => new Set(s.toLowerCase().match(/[a-z0-9]{3,}/g) ?? []);
export function similarity(a: string, b: string): number {
  const A = words(a), B = words(b);
  const inter = [...A].filter((w) => B.has(w)).length;
  return inter / (A.size + B.size - inter || 1);
}

export async function extract(m: Meeting, llm?: LLMClient): Promise<Result> {
  const fallback = regexExtract(m);
  if (!llm) return { meeting: m, source: "regex", extraction: fallback, warnings: ["no LLM configured"], possibleMisses: [] };
  try {
    const text = await llm.complete(EXTRACT_SYSTEM, buildPrompt(m));
    const json = JSON.parse(text.slice(text.indexOf("{"), text.lastIndexOf("}") + 1));
    const { extraction, warnings } = validate(json, m);
    const possibleMisses = fallback.actions.filter(
      (r) => !extraction.actions.some((a) => a.evidence === r.evidence || similarity(a.task, r.task) >= 0.4));
    return { meeting: m, source: "llm", extraction, warnings, possibleMisses };
  } catch (e) {
    return { meeting: m, source: "regex", extraction: fallback, warnings: [`LLM failed (${(e as Error).message}); used regex fallback`], possibleMisses: [] };
  }
}
