// Deterministic, zero-cost repairs applied before spending another LLM call.
import { type Schema, typeOf } from "./schema.ts";

export interface Parsed {
  value?: unknown;
  error?: string;
  fixes: string[];
}

/** Pull a JSON object out of chatty model output and fix the syntax slips models commonly make. */
export function extractJson(text: string): Parsed {
  const fixes: string[] = [];
  let s = text.trim();
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) {
    s = fence[1].trim();
    fixes.push("stripped code fence");
  }
  const start = s.indexOf("{");
  const end = s.lastIndexOf("}");
  if (start === -1 || end <= start) return { error: "no JSON object found", fixes };
  if (start > 0 || end < s.length - 1) fixes.push("stripped surrounding prose");
  s = s.slice(start, end + 1);
  try {
    return { value: JSON.parse(s), fixes };
  } catch {
    // fall through to syntax repairs
  }
  const repaired = s
    .replace(/,\s*([}\]])/g, "$1") // trailing commas
    .replace(/([{,]\s*)'([^']+)'\s*:/g, '$1"$2":') // single-quoted keys
    .replace(/:\s*'([^']*)'/g, ': "$1"') // single-quoted values
    .replace(/([{,]\s*)([A-Za-z_]\w*)\s*:/g, '$1"$2":'); // bare keys
  try {
    const value = JSON.parse(repaired);
    fixes.push("repaired JSON syntax");
    return { value, fixes };
  } catch (e) {
    return { error: `invalid JSON: ${(e as Error).message}`, fixes };
  }
}

/** Schema-guided coercions that cannot change meaning: "1,850" -> 1850 for numbers, "USD " -> "USD",
 *  enum case ("Expedite" -> "expedite"). Anything that needs judgment is left for the model. */
export function coerce(value: unknown, schema: Schema, path = "$", fixes: string[] = []): unknown {
  const t = typeOf(value);
  if ((schema.type === "number" || schema.type === "integer") && t === "string") {
    const cleaned = (value as string).replace(/[$€£,\s]|USD|EUR|GBP/g, "");
    const n = Number(cleaned);
    if (cleaned !== "" && Number.isFinite(n) && (schema.type === "number" || Number.isInteger(n))) {
      fixes.push(`${path}: "${value}" -> ${n}`);
      return n;
    }
  }
  if (schema.type === "string" && t === "string") {
    let s = value as string;
    if (s !== s.trim()) s = s.trim();
    if (schema.enum && !schema.enum.includes(s)) {
      const hit = schema.enum.find((e) => typeof e === "string" && e.toLowerCase() === s.toLowerCase());
      if (hit !== undefined) s = hit as string;
    }
    if (s !== value) fixes.push(`${path}: "${value}" -> "${s}"`);
    return s;
  }
  if (schema.type === "array" && Array.isArray(value) && schema.items) {
    return value.map((v, i) => coerce(v, schema.items!, `${path}[${i}]`, fixes));
  }
  if (schema.type === "object" && t === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = schema.properties?.[k] ? coerce(v, schema.properties[k], `${path}.${k}`, fixes) : v;
    }
    return out;
  }
  return value;
}
