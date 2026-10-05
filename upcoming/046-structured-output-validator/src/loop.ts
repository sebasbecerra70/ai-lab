// Generate -> parse -> local repair -> validate -> (re-ask with the exact errors) until valid or out of attempts.
import type { LLMClient } from "./llm.ts";
import { coerce, extractJson } from "./repair.ts";
import { type Schema, type ValidationError, formatErrors, validate } from "./schema.ts";

export interface Attempt {
  raw: string;
  localFixes: string[];
  errors: ValidationError[];
}

export interface Result<T = unknown> {
  ok: boolean;
  value?: T;
  attempts: Attempt[];
  llmCalls: number;
}

export interface Options {
  maxAttempts?: number;
  localRepair?: boolean;
}

export const SYSTEM =
  "Extract the purchase order from the email as a single JSON object that conforms to the JSON Schema. " +
  "Use only facts stated in the email. Reply with JSON only.";

export function buildPrompt(id: string, input: string, schema: Schema, attempt: number, last?: Attempt): string {
  const parts = [`ID: ${id}`, `ATTEMPT: ${attempt}`, `SCHEMA:\n${JSON.stringify(schema)}`, `EMAIL:\n${input}`];
  if (last) {
    parts.push(`YOUR PREVIOUS OUTPUT:\n${last.raw}`);
    parts.push(`IT FAILED VALIDATION:\n${formatErrors(last.errors)}`);
    parts.push("Return the corrected JSON object only. If the email does not contain a required value, do not invent one.");
  }
  return parts.join("\n\n");
}

/** Validate one model output, applying zero-cost repairs first when enabled. */
export function check(raw: string, schema: Schema, localRepair = true): Attempt & { value?: unknown } {
  if (!localRepair) {
    try {
      const value = JSON.parse(raw);
      return { raw, localFixes: [], errors: validate(value, schema), value };
    } catch (e) {
      return { raw, localFixes: [], errors: [{ path: "$", message: `invalid JSON: ${(e as Error).message}` }] };
    }
  }
  const parsed = extractJson(raw);
  if (parsed.error) return { raw, localFixes: parsed.fixes, errors: [{ path: "$", message: parsed.error }] };
  const fixes = [...parsed.fixes];
  const value = coerce(parsed.value, schema, "$", fixes);
  return { raw, localFixes: fixes, errors: validate(value, schema), value };
}

export async function generateValidated<T>(llm: LLMClient, schema: Schema, id: string, input: string, opts: Options = {}): Promise<Result<T>> {
  const { maxAttempts = 3, localRepair = true } = opts;
  const attempts: Attempt[] = [];
  for (let n = 1; n <= maxAttempts; n++) {
    const raw = await llm.complete(SYSTEM, buildPrompt(id, input, schema, n, attempts.at(-1)));
    const { value, ...attempt } = check(raw, schema, localRepair);
    attempts.push(attempt);
    if (attempt.errors.length === 0) return { ok: true, value: value as T, attempts, llmCalls: n };
  }
  return { ok: false, attempts, llmCalls: maxAttempts };
}
