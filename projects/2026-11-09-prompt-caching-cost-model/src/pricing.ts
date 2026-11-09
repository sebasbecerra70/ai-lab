// Anthropic list prices in USD per million tokens, and prompt-caching rules.

export interface ModelPrice {
  id: string;
  input: number;
  output: number;
  cacheRead: number;
  minCacheableTokens: number; // shorter prefixes silently don't cache
}

export const MODELS: Record<string, ModelPrice> = {
  "claude-opus-5-5": { id: "claude-opus-5-5", input: 4, output: 20, cacheRead: 0.2, minCacheableTokens: 512 },
  "claude-sonnet-5-5": { id: "claude-sonnet-5-5", input: 2, output: 10, cacheRead: 0.2, minCacheableTokens: 512 },
  "claude-haiku-4-5": { id: "claude-haiku-4-5", input: 1, output: 5, cacheRead: 0.1, minCacheableTokens: 4096 },
};

export type Ttl = "none" | "5m" | "1h";

export const TTL_SECONDS: Record<Exclude<Ttl, "none">, number> = { "5m": 300, "1h": 3600 };

/** Cache writes cost a premium over base input: 1.25x for 5 minutes, 2x for 1 hour. */
export const WRITE_MULTIPLIER: Record<Exclude<Ttl, "none">, number> = { "5m": 1.25, "1h": 2 };

export function usd(tokens: number, perMTok: number): number {
  return (tokens * perMTok) / 1_000_000;
}
