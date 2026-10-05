// Seeded random numbers so every simulation is reproducible: uniform, normal, gamma and beta draws.

export class Rng {
  private s: number;
  constructor(seed: number) {
    this.s = seed >>> 0;
  }

  /** mulberry32: small, fast, and good enough for simulation. */
  next(): number {
    this.s = (this.s + 0x6d2b79f5) >>> 0;
    let t = this.s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  int(n: number): number {
    return Math.floor(this.next() * n);
  }

  normal(): number {
    const u = 1 - this.next();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * this.next());
  }

  /** Marsaglia-Tsang gamma sampler; shape < 1 uses the boost trick. */
  gamma(shape: number): number {
    if (shape < 1) return this.gamma(shape + 1) * Math.pow(this.next(), 1 / shape);
    const d = shape - 1 / 3;
    const c = 1 / Math.sqrt(9 * d);
    for (;;) {
      let x: number;
      let v: number;
      do {
        x = this.normal();
        v = 1 + c * x;
      } while (v <= 0);
      v = v * v * v;
      const u = this.next();
      if (u < 1 - 0.0331 * x ** 4 || Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
    }
  }

  beta(a: number, b: number): number {
    const x = this.gamma(a);
    return x / (x + this.gamma(b));
  }
}
