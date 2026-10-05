// How much should we trust the ranking? One-at-a-time swings plus a Monte Carlo over input uncertainty.
import { type Feature, riceScore } from "./rice.ts";

/** Small seeded PRNG (mulberry32) so simulations are reproducible in tests and reviews. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function ranks(features: Feature[], scores: number[]): Map<string, number> {
  const order = features.map((f, i) => ({ id: f.id, s: scores[i] })).sort((a, b) => b.s - a.s || a.id.localeCompare(b.id));
  return new Map(order.map((o, i) => [o.id, i + 1]));
}

export interface Swing {
  id: string;
  factor: "reach" | "impact" | "confidence" | "effort";
  worstRankChange: number;
}

/** For each feature and factor, move that one input ±pct and record the largest rank move it causes. */
export function oneAtATime(features: Feature[], pct = 0.3): Swing[] {
  const base = ranks(features, features.map(riceScore));
  const out: Swing[] = [];
  for (const f of features) {
    for (const factor of ["reach", "impact", "confidence", "effort"] as const) {
      let worst = 0;
      for (const dir of [-1, 1]) {
        const scores = features.map((g) => {
          if (g.id !== f.id) return riceScore(g);
          const v = g[factor] * (1 + dir * pct);
          return riceScore({ ...g, [factor]: factor === "confidence" ? Math.min(1, v) : v });
        });
        worst = Math.max(worst, Math.abs(ranks(features, scores).get(f.id)! - base.get(f.id)!));
      }
      out.push({ id: f.id, factor, worstRankChange: worst });
    }
  }
  return out;
}

export interface Uncertainty {
  reach: number; // relative half-width, e.g. 0.3 = ±30%
  effort: number;
}

export interface TopNOdds {
  id: string;
  pTopN: number;
  p10Rank: number;
  p90Rank: number;
  verdict: "robust in" | "robust out" | "contested";
}

/**
 * Monte Carlo: reach and effort estimates are the shakiest inputs, so sample them uniformly within ±band.
 * Confidence widens the band: a 50%-confidence estimate gets twice the spread of a 100% one.
 */
export function monteCarlo(features: Feature[], topN: number, runs = 2000, seed = 42,
  band: Uncertainty = { reach: 0.3, effort: 0.4 }): TopNOdds[] {
  const rand = mulberry32(seed);
  const hits = new Map(features.map((f) => [f.id, 0]));
  const samples = new Map(features.map((f) => [f.id, [] as number[]]));
  for (let r = 0; r < runs; r++) {
    const scores = features.map((f) => {
      const widen = 1 / f.confidence;
      const reach = f.reach * (1 + (rand() * 2 - 1) * band.reach * widen);
      const effort = Math.max(0.1, f.effort * (1 + (rand() * 2 - 1) * band.effort * widen));
      return riceScore({ ...f, reach: Math.max(0, reach), effort });
    });
    for (const [id, rk] of ranks(features, scores)) {
      samples.get(id)!.push(rk);
      if (rk <= topN) hits.set(id, hits.get(id)! + 1);
    }
  }
  return features.map((f) => {
    const s = samples.get(f.id)!.sort((a, b) => a - b);
    const p = hits.get(f.id)! / runs;
    const verdict = p >= 0.75 ? "robust in" : p <= 0.25 ? "robust out" : "contested";
    return { id: f.id, pTopN: p, p10Rank: s[Math.floor(runs * 0.1)], p90Rank: s[Math.floor(runs * 0.9)], verdict };
  });
}
