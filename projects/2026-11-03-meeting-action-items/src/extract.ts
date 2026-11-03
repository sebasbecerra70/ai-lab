// Shared types, notes parsing and the regex extractor (the fallback when no LLM is available or it fails).
import { DUE_PATTERN, parseISO, resolveDue } from "./dates.ts";

export interface Meeting {
  title: string;
  date: string; // ISO
  attendees: string[];
  body: string;
}

export interface ActionItem {
  owner: string | null; // full attendee name, or null when nobody was named
  task: string;
  due: string | null; // ISO
  evidence: string; // the line it came from, so a reviewer can check it
}

export interface Extraction {
  actions: ActionItem[];
  decisions: { text: string; evidence: string }[];
}

export function parseNotes(text: string): Meeting {
  const lines = text.split("\n");
  const title = (lines.find((l) => l.startsWith("# ")) ?? "# Untitled").slice(2).trim();
  const field = (name: string) => lines.find((l) => l.toLowerCase().startsWith(`${name}:`))?.split(":").slice(1).join(":").trim();
  const date = field("date");
  if (!date) throw new Error("notes need a 'Date: YYYY-MM-DD' line");
  parseISO(date);
  const attendees = (field("attendees") ?? "").split(",").map((a) => a.replace(/\(.*?\)/, "").trim()).filter(Boolean);
  const body = lines.filter((l) => !l.startsWith("# ") && !/^(date|attendees):/i.test(l)).join("\n").trim();
  return { title, date, attendees, body };
}

/** Map "Jen", "@sam" or "Priya Shah" to the attendee's full name. */
export function matchAttendee(name: string, attendees: string[]): string | null {
  const n = name.replace(/^@/, "").trim().toLowerCase();
  if (!n) return null;
  return attendees.find((a) => a.toLowerCase() === n || a.split(" ")[0].toLowerCase() === n) ?? null;
}

const DECISION = /^(?:decision|decided|agreed)(?:\s+that)?\s*:?\s*(.+)$/i;
const ACTION_TAG = /^(?:action(?: item)?|todo|ai)\s*:\s*(.+)$/i;
const OWNER_VERB = /^(@?[A-Za-z]+)\s+(?:will|to|owns|needs to|is going to)\s+(.+)$/i;
const UNOWNED = /^(?:someone|somebody|we)\s+(?:should|need to|needs to)\s+(.+)$/i;

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function cleanTask(s: string): string {
  return capitalize(s.replace(DUE_PATTERN, "").replace(/\s*,\s*$/, "").replace(/[\s.,;]+$/, "").replace(/\s{2,}/g, " ").trim());
}

function sentences(body: string): string[] {
  return body.split("\n").flatMap((line) =>
    line.replace(/^\s*[-*]\s*/, "").split(/(?<=[a-z0-9)%])\.\s+(?=[A-Z@])/).map((s) => s.trim()).filter(Boolean));
}

export function regexExtract(m: Meeting): Extraction {
  const meeting = parseISO(m.date);
  const out: Extraction = { actions: [], decisions: [] };
  for (const s of sentences(m.body)) {
    const dec = DECISION.exec(s) ?? /\bwe (?:decided|agreed) (?:to |that )?(.+)$/i.exec(s);
    if (dec) {
      out.decisions.push({ text: capitalize(dec[1].replace(/\.$/, "")), evidence: s });
      continue;
    }
    const inner = ACTION_TAG.exec(s)?.[1] ?? s;
    const owned = OWNER_VERB.exec(inner);
    const ownerName = owned ? matchAttendee(owned[1], m.attendees) : null;
    const unowned = UNOWNED.exec(inner);
    if (!(owned && ownerName) && !unowned && inner === s && !/^@\w+/.test(s)) continue;
    let owner = ownerName;
    let task = owned && ownerName ? owned[2] : unowned ? unowned[1] : inner;
    const handle = /^@(\w+)\s+(.+)$/.exec(inner);
    if (!owner && handle) {
      owner = matchAttendee(handle[1], m.attendees);
      task = handle[2];
    }
    const due = DUE_PATTERN.exec(task);
    out.actions.push({ owner, task: cleanTask(task), due: due ? resolveDue(due[1], meeting) : null, evidence: s });
  }
  return out;
}
