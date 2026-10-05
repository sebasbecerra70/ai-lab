// Replay arrivals against a single shared prefix cache and price every request.
import { type ModelPrice, TTL_SECONDS, type Ttl, WRITE_MULTIPLIER, usd } from "./pricing.ts";

export interface Workload {
  prefixTokens: number; // stable system prompt + tools + reference docs
  dynamicTokens: number; // per-request user content after the cache breakpoint
  outputTokens: number;
}

export interface SimResult {
  requests: number;
  writes: number;
  hits: number;
  costUsd: number;
  inputCostUsd: number;
  outputCostUsd: number;
  hitRate: number;
  cacheable: boolean;
}

/**
 * Each read refreshes the entry; the lifetime is measured from request start.
 * We assume requests are serialized enough that a write lands before the next
 * request reads (true for gaps over a few seconds; concurrent cold starts would
 * each pay a write in reality, so this is slightly optimistic at burst onset).
 */
export function simulate(arrivals: number[], w: Workload, m: ModelPrice, ttl: Ttl): SimResult {
  const cacheable = ttl !== "none" && w.prefixTokens >= m.minCacheableTokens;
  let expiresAt = -Infinity;
  let writes = 0;
  let hits = 0;
  let input = 0;
  for (const t of arrivals) {
    input += usd(w.dynamicTokens, m.input);
    if (!cacheable) {
      input += usd(w.prefixTokens, m.input);
      continue;
    }
    const life = TTL_SECONDS[ttl as Exclude<Ttl, "none">];
    if (t < expiresAt) {
      hits++;
      input += usd(w.prefixTokens, m.cacheRead);
    } else {
      writes++;
      input += usd(w.prefixTokens, m.input * WRITE_MULTIPLIER[ttl as Exclude<Ttl, "none">]);
    }
    expiresAt = t + life;
  }
  const output = usd(w.outputTokens * arrivals.length, m.output);
  return {
    requests: arrivals.length,
    writes,
    hits,
    costUsd: input + output,
    inputCostUsd: input,
    outputCostUsd: output,
    hitRate: arrivals.length ? hits / arrivals.length : 0,
    cacheable,
  };
}

/** Minimum reads per write for caching to beat no caching on the prefix. */
export function breakEvenReads(m: ModelPrice, ttl: Exclude<Ttl, "none">): number {
  // write premium paid once must be recovered by (input - cacheRead) per read
  const premium = m.input * (WRITE_MULTIPLIER[ttl] - 1);
  return Math.ceil(premium / (m.input - m.cacheRead) - 1e-12);
}

export interface Recommendation {
  ttl: Ttl;
  costUsd: number;
  savingsVsNone: number;
}

export function recommend(arrivals: number[], w: Workload, m: ModelPrice): { results: Record<Ttl, SimResult>; best: Recommendation } {
  const results = {
    none: simulate(arrivals, w, m, "none"),
    "5m": simulate(arrivals, w, m, "5m"),
    "1h": simulate(arrivals, w, m, "1h"),
  } as Record<Ttl, SimResult>;
  const ttl = (Object.keys(results) as Ttl[]).reduce((a, b) => (results[b].costUsd < results[a].costUsd - 1e-12 ? b : a), "none");
  return { results, best: { ttl, costUsd: results[ttl].costUsd, savingsVsNone: 1 - results[ttl].costUsd / results.none.costUsd } };
}
