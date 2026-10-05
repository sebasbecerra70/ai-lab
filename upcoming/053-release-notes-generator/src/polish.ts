// LLM polish: rewrite commit subjects for customers, then accept each rewrite only if it keeps the facts.
import type { LLMClient } from "./llm.ts";
import { type Item, type Notes } from "./notes.ts";

export const SYSTEM =
  "You rewrite engineering commit subjects as customer-facing release note bullets. Plain language, " +
  "present tense, describe the benefit, no internal jargon. Keep every number exactly. Do not add features, " +
  "issue numbers or claims that are not in the input. Return a JSON object mapping each id to its rewritten text.";

export interface PolishResult {
  text: Record<string, string>; // id -> accepted rewrite (missing = keep original)
  rejected: { id: string; reason: string; proposed?: string }[];
}

function kindOf(notes: Notes, id: string): string {
  if (notes.breaking.some((i) => i.id === id)) return "breaking";
  if (notes.features.some((i) => i.id === id)) return "feature";
  if (notes.fixes.some((i) => i.id === id)) return "fix";
  return "performance";
}

export function buildPrompt(items: Item[], notes: Notes, jargon: Record<string, string>): string {
  const lines = Object.entries(jargon).map(([k, v]) => `GLOSSARY ${k} => ${v}`);
  lines.push("ITEMS (id | kind | subject):");
  for (const i of items) lines.push(`${i.id} | ${kindOf(notes, i.id)} | ${i.text}`);
  return lines.join("\n");
}

const numbers = (s: string) => s.match(/\d+(?:\.\d+)?/g) ?? [];

export function checkRewrite(original: string, proposed: unknown): string | null {
  if (typeof proposed !== "string" || !proposed.trim()) return "empty or not a string";
  if (proposed.length > 160) return "longer than 160 characters";
  if (/#\d+/.test(proposed)) return "added an issue reference"; // refs are appended by the renderer, never the model
  const missing = numbers(original).filter((n) => !numbers(proposed).includes(n));
  if (missing.length) return `dropped number(s) ${missing.join(", ")}`;
  const invented = numbers(proposed).filter((n) => !numbers(original).includes(n));
  if (invented.length) return `introduced number(s) ${invented.join(", ")}`;
  return null;
}

export async function polish(llm: LLMClient, items: Item[], notes: Notes, jargon: Record<string, string>): Promise<PolishResult> {
  const raw = await llm.complete(SYSTEM, buildPrompt(items, notes, jargon));
  const json = raw.match(/\{[\s\S]*\}/)?.[0];
  let parsed: Record<string, unknown> = {};
  try {
    parsed = json ? JSON.parse(json) : {};
  } catch {
    return { text: {}, rejected: items.map((i) => ({ id: i.id, reason: "model output was not JSON" })) };
  }
  const result: PolishResult = { text: {}, rejected: [] };
  for (const i of items) {
    if (!(i.id in parsed)) {
      result.rejected.push({ id: i.id, reason: "missing from model output" });
      continue;
    }
    const why = checkRewrite(i.text, parsed[i.id]);
    if (why) result.rejected.push({ id: i.id, reason: why, proposed: String(parsed[i.id]) });
    else result.text[i.id] = parsed[i.id] as string;
  }
  for (const extra of Object.keys(parsed).filter((k) => !items.some((i) => i.id === k))) {
    result.rejected.push({ id: extra, reason: "unknown id invented by the model" });
  }
  return result;
}
