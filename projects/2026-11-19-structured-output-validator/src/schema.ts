// A small, dependency-free JSON Schema validator (the subset LLM extraction schemas actually use).

export interface Schema {
  type?: "object" | "array" | "string" | "number" | "integer" | "boolean" | "null";
  properties?: Record<string, Schema>;
  required?: string[];
  additionalProperties?: boolean;
  items?: Schema;
  minItems?: number;
  enum?: unknown[];
  minimum?: number;
  maximum?: number;
  minLength?: number;
  pattern?: string;
  format?: "date" | "email";
}

export interface ValidationError {
  path: string; // JSON pointer-ish: $.lines[0].qty
  message: string;
}

const FORMATS: Record<string, (s: string) => boolean> = {
  date: (s) => /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s)) && new Date(s).toISOString().startsWith(s),
  email: (s) => /^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(s),
};

export function typeOf(v: unknown): string {
  if (v === null) return "null";
  if (Array.isArray(v)) return "array";
  if (typeof v === "number") return Number.isInteger(v) ? "integer" : "number";
  return typeof v;
}

export function validate(value: unknown, schema: Schema, path = "$"): ValidationError[] {
  const errors: ValidationError[] = [];
  const err = (message: string) => errors.push({ path, message });
  const t = typeOf(value);

  if (schema.type) {
    const ok = schema.type === t || (schema.type === "number" && t === "integer");
    if (!ok) {
      err(`expected ${schema.type}, got ${t}${t === "string" ? ` "${value}"` : ""}`);
      return errors; // nothing else is meaningful on the wrong type
    }
  }
  if (schema.enum && !schema.enum.includes(value)) err(`must be one of ${schema.enum.map((e) => JSON.stringify(e)).join(", ")}, got ${JSON.stringify(value)}`);

  if (typeof value === "string") {
    if (schema.minLength !== undefined && value.length < schema.minLength) err(`shorter than ${schema.minLength} chars`);
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) err(`"${value}" does not match ${schema.pattern}`);
    if (schema.format && !FORMATS[schema.format](value)) err(`"${value}" is not a valid ${schema.format}`);
  }
  if (typeof value === "number") {
    if (schema.minimum !== undefined && value < schema.minimum) err(`${value} is below minimum ${schema.minimum}`);
    if (schema.maximum !== undefined && value > schema.maximum) err(`${value} is above maximum ${schema.maximum}`);
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) err(`needs at least ${schema.minItems} item(s)`);
    if (schema.items) value.forEach((v, i) => errors.push(...validate(v, schema.items!, `${path}[${i}]`)));
  }
  if (t === "object") {
    const obj = value as Record<string, unknown>;
    for (const k of schema.required ?? []) if (!(k in obj)) errors.push({ path: `${path}.${k}`, message: "is required" });
    for (const [k, v] of Object.entries(obj)) {
      const sub = schema.properties?.[k];
      if (sub) errors.push(...validate(v, sub, `${path}.${k}`));
      else if (schema.additionalProperties === false) errors.push({ path: `${path}.${k}`, message: "is not allowed" });
    }
  }
  return errors;
}

export function formatErrors(errors: ValidationError[]): string {
  return errors.map((e) => `- ${e.path} ${e.message}`).join("\n");
}
