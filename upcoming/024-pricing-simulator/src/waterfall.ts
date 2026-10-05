// Pocket-price waterfall: from list price to what the business actually keeps per unit, and discount break-even math.

export interface Deal {
  customer: string;
  sku: string;
  units: number;
  volumeDiscountPct: number;
  promoDiscountPct: number;
  rebatePct: number; // paid back after the invoice, so it's invisible on the invoice price
  paymentTermsDays: number;
  freightPerUnit: number;
}

export interface Step {
  label: string;
  amount: number; // per unit, negative for leakage
  running: number;
}

export const COST_OF_CAPITAL = 0.09; // annual, used to price extended payment terms
const STANDARD_TERMS_DAYS = 30;

export function waterfall(listPrice: number, unitCost: number, d: Deal): Step[] {
  const steps: Step[] = [];
  let p = listPrice;
  // Leakage rows that cost nothing on this deal (no promo, standard terms) are skipped to keep the waterfall readable.
  const push = (label: string, amount: number) => {
    if (amount === 0) return;
    p += amount;
    steps.push({ label, amount, running: p });
  };
  steps.push({ label: "list price", amount: listPrice, running: listPrice });
  push("volume discount", -listPrice * (d.volumeDiscountPct / 100));
  push("promo discount", -p * (d.promoDiscountPct / 100));
  steps.push({ label: "= invoice price", amount: 0, running: p });
  push("rebate", -p * (d.rebatePct / 100));
  const extraDays = Math.max(0, d.paymentTermsDays - STANDARD_TERMS_DAYS);
  push(`payment terms (${d.paymentTermsDays}d)`, -p * COST_OF_CAPITAL * (extraDays / 365));
  push("freight", -d.freightPerUnit);
  steps.push({ label: "= pocket price", amount: 0, running: p });
  push("unit cost", -unitCost);
  steps.push({ label: "= pocket margin", amount: 0, running: p });
  return steps;
}

export function pocketMargin(steps: Step[]): number {
  return steps[steps.length - 1].running;
}

/** Extra volume needed for a price cut to keep gross profit flat: d / (m - d), with m the margin % of price. */
export function breakEvenVolumeIncrease(discountPct: number, marginPct: number): number {
  const d = discountPct / 100;
  const m = marginPct / 100;
  if (d >= m) return Infinity; // discounting below cost can't be made up with volume
  return (d / (m - d)) * 100;
}
