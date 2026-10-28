import assert from "node:assert/strict";
import { test } from "node:test";
import { breakEvenVolumeIncrease, COST_OF_CAPITAL, type Deal, pocketMargin, waterfall } from "./waterfall.ts";

const deal = (over: Partial<Deal> = {}): Deal => ({
  customer: "Acme", sku: "X", units: 100, volumeDiscountPct: 10, promoDiscountPct: 5, rebatePct: 2,
  paymentTermsDays: 30, freightPerUnit: 1, ...over,
});
const close = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

test("discounts compound: promo applies to the already volume-discounted price", () => {
  const steps = waterfall(100, 60, deal());
  const invoice = steps.find((s) => s.label === "= invoice price")!;
  close(invoice.running, 100 * 0.9 * 0.95);
});

test("pocket margin is list minus every leakage minus cost", () => {
  const steps = waterfall(100, 60, deal());
  const pocket = 85.5 * 0.98 - 1;
  close(steps.find((s) => s.label === "= pocket price")!.running, pocket);
  close(pocketMargin(steps), pocket - 60);
  const leak = steps.filter((s) => !s.label.startsWith("=") && s.label !== "list price").reduce((t, s) => t + s.amount, 0);
  close(100 + leak, pocketMargin(steps));
});

test("payment terms beyond 30 days cost the carrying interest on the net price", () => {
  const steps = waterfall(100, 60, deal({ volumeDiscountPct: 0, promoDiscountPct: 0, rebatePct: 0, paymentTermsDays: 90 }));
  const terms = steps.find((s) => s.label.startsWith("payment terms"))!;
  close(terms.amount, -100 * COST_OF_CAPITAL * (60 / 365));
});

test("zero-value leakage rows are dropped but subtotals stay", () => {
  const steps = waterfall(100, 60, deal({ promoDiscountPct: 0, rebatePct: 0, freightPerUnit: 0 }));
  assert.deepEqual(steps.map((s) => s.label), [
    "list price", "volume discount", "= invoice price", "= pocket price", "unit cost", "= pocket margin",
  ]);
  close(pocketMargin(steps), 30);
});

test("break-even volume for a price cut is d / (m - d), and never when the cut exceeds the margin", () => {
  close(breakEvenVolumeIncrease(10, 40), 100 / 3);
  close(breakEvenVolumeIncrease(15, 30), 100);
  assert.equal(breakEvenVolumeIncrease(20, 20), Infinity);
});
