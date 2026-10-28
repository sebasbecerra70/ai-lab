// Price elasticity: fit a constant-elasticity demand curve (log-log OLS) and run what-if price changes.

export interface Observation {
  price: number;
  units: number;
}

export interface ElasticityFit {
  elasticity: number; // % change in units per 1% change in price (negative for normal goods)
  intercept: number; // ln(units) at ln(price) = 0
  r2: number;
  n: number;
}

export function fitElasticity(history: Observation[]): ElasticityFit {
  const pts = history.filter((h) => h.price > 0 && h.units > 0).map((h) => [Math.log(h.price), Math.log(h.units)]);
  if (pts.length < 3) throw new Error("need at least 3 positive price/volume observations");
  const n = pts.length;
  const mx = pts.reduce((s, [x]) => s + x, 0) / n;
  const my = pts.reduce((s, [, y]) => s + y, 0) / n;
  const sxx = pts.reduce((s, [x]) => s + (x - mx) ** 2, 0);
  if (sxx === 0) throw new Error("price never changed: elasticity is not identifiable");
  const sxy = pts.reduce((s, [x, y]) => s + (x - mx) * (y - my), 0);
  const slope = sxy / sxx;
  const intercept = my - slope * mx;
  const ssTot = pts.reduce((s, [, y]) => s + (y - my) ** 2, 0);
  const ssRes = pts.reduce((s, [x, y]) => s + (y - (intercept + slope * x)) ** 2, 0);
  return { elasticity: slope, intercept, r2: ssTot ? 1 - ssRes / ssTot : 1, n };
}

export interface WhatIf {
  priceChangePct: number;
  price: number;
  units: number;
  revenue: number;
  grossProfit: number;
  profitDeltaPct: number;
}

/** Constant elasticity: Q1 = Q0 * (P1 / P0)^e, anchored at today's price and volume. */
export function whatIf(listPrice: number, unitCost: number, units: number, elasticity: number, changesPct: number[]): WhatIf[] {
  const base = (listPrice - unitCost) * units;
  return changesPct.map((pct) => {
    const price = listPrice * (1 + pct / 100);
    const q = units * (price / listPrice) ** elasticity;
    const gp = (price - unitCost) * q;
    return { priceChangePct: pct, price, units: q, revenue: price * q, grossProfit: gp, profitDeltaPct: ((gp - base) / base) * 100 };
  });
}

/**
 * Profit-maximizing price. With constant elasticity e < -1 the closed form is P* = c * e / (1 + e).
 * For inelastic demand (e >= -1) profit rises without bound in this model, so we cap at the search ceiling
 * and say so: the model is only trusted near observed prices.
 */
export function optimalPrice(unitCost: number, elasticity: number, floor: number, ceiling: number): { price: number; bounded: boolean } {
  if (elasticity < -1) {
    const p = (unitCost * elasticity) / (1 + elasticity);
    return { price: Math.min(Math.max(p, floor), ceiling), bounded: p < floor || p > ceiling };
  }
  return { price: ceiling, bounded: true };
}
