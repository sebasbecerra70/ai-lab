// Deterministic synthetic traffic: request start times (seconds) over a horizon.

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

/** Poisson arrivals with a time-varying rate (requests per hour), via thinning. */
export function poissonArrivals(rateAt: (t: number) => number, maxRate: number, horizonS: number, seed: number): number[] {
  const rnd = mulberry32(seed);
  const out: number[] = [];
  let t = 0;
  for (;;) {
    t += -Math.log(1 - rnd()) / (maxRate / 3600);
    if (t >= horizonS) return out;
    if (rnd() < rateAt(t) / maxRate) out.push(t);
  }
}

export interface Pattern {
  name: string;
  description: string;
  arrivals: number[];
}

const DAY = 24 * 3600;

export function standardPatterns(seed = 42): Pattern[] {
  const hour = (t: number) => (t / 3600) % 24;
  return [
    { name: "steady", description: "support bot, 120 req/h around the clock", arrivals: poissonArrivals(() => 120, 120, DAY, seed) },
    {
      name: "business-hours",
      description: "internal copilot, 200 req/h 9-17, 4 req/h otherwise",
      arrivals: poissonArrivals((t) => (hour(t) >= 9 && hour(t) < 17 ? 200 : 4), 200, DAY, seed + 1),
    },
    {
      name: "bursty",
      description: "batch-ish jobs: 10-minute bursts of 600 req/h, every 2 hours",
      arrivals: poissonArrivals((t) => (t % 7200 < 600 ? 600 : 0), 600, DAY, seed + 2),
    },
    { name: "sparse", description: "niche tool, 3 req/h", arrivals: poissonArrivals(() => 3, 3, DAY, seed + 3) },
  ];
}
