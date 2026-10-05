// RICE scoring: Reach × Impact × Confidence ÷ Effort, with input validation on the standard scales.

export interface Feature {
  id: string;
  name: string;
  reach: number; // users or accounts affected per quarter
  impact: number; // 0.25 minimal, 0.5 low, 1 medium, 2 high, 3 massive
  confidence: number; // 0.5 low, 0.8 medium, 1.0 high
  effort: number; // person-months
  notes?: string;
  dependsOn?: string[];
}

export interface Scored extends Feature {
  score: number;
  rank: number;
}

export const IMPACT_SCALE = [0.25, 0.5, 1, 2, 3];

export function validate(f: Feature): string[] {
  const errors: string[] = [];
  if (!f.id) errors.push("missing id");
  if (!(f.reach >= 0)) errors.push(`${f.id}: reach must be >= 0`);
  if (!IMPACT_SCALE.includes(f.impact)) errors.push(`${f.id}: impact must be one of ${IMPACT_SCALE.join(", ")}`);
  if (!(f.confidence > 0 && f.confidence <= 1)) errors.push(`${f.id}: confidence must be in (0, 1]`);
  if (!(f.effort > 0)) errors.push(`${f.id}: effort must be > 0`);
  return errors;
}

export function riceScore(f: Pick<Feature, "reach" | "impact" | "confidence" | "effort">): number {
  return (f.reach * f.impact * f.confidence) / f.effort;
}

export function rank(features: Feature[]): Scored[] {
  const errors = features.flatMap(validate);
  const ids = new Set<string>();
  for (const f of features) {
    if (ids.has(f.id)) errors.push(`duplicate id ${f.id}`);
    ids.add(f.id);
  }
  for (const f of features) {
    for (const d of f.dependsOn ?? []) if (!ids.has(d)) errors.push(`${f.id}: unknown dependency ${d}`);
  }
  if (errors.length) throw new Error(errors.join("; "));
  return features
    .map((f) => ({ ...f, score: riceScore(f), rank: 0 }))
    .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id))
    .map((f, i) => ({ ...f, rank: i + 1 }));
}
