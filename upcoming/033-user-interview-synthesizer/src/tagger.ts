// Codebook-based theme tagging plus a tiny sentiment lexicon.

export interface Theme {
  name: string;
  keywords: string[];
}

export const CODEBOOK: Theme[] = [
  { name: "Onboarding & setup", keywords: ["setup", "onboarding", "getting started", "import", "live in", "first week", "checklist", "sample data"] },
  { name: "Pricing & packaging", keywords: ["pricing", "price", "tier", "per-seat", "pay more", "renewal", "starter plan", "justify"] },
  { name: "Integrations", keywords: ["integration", "connector", "connected", "wms", "erp", "netsuite", "shopify", "sap"] },
  { name: "Reporting & export", keywords: ["report", "export", "csv", "pdf", "filter", "excel"] },
  { name: "Performance", keywords: ["slow when", "slowly", "is slow", "to load", "seconds", "crash"] },
  { name: "Support", keywords: ["support", "reply", "answered"] },
  { name: "Collaboration", keywords: ["collaborate", "comment", "tag teammates", "share", "notes for", "edit at a time", "slack"] },
  { name: "Alerts & monitoring", keywords: ["alert", "stockout", "caught"] },
];

const POSITIVE = ["great", "love", "best", "fast", "easy", "accurate", "trusts", "saved", "helped", "quick", "reason we bought"];
const NEGATIVE = ["confusing", "breaks", "slow", "painful", "useless", "crashes", "cuts off", "can't", "cannot", "could not", "no way", "hesitate", "skipped", "failed", "by hand", "waited", "jumped", "too long", "wish", "nobody"];

export type Sentiment = -1 | 0 | 1;

function hits(text: string, words: string[]): number {
  const low = text.toLowerCase();
  return words.filter((w) => new RegExp(`\\b${w.replace(/[-]/g, "\\-")}`, "i").test(low)).length;
}

export function tagThemes(text: string, codebook: Theme[] = CODEBOOK): string[] {
  return codebook.filter((t) => hits(text, t.keywords) > 0).map((t) => t.name);
}

export function sentiment(text: string): Sentiment {
  const score = hits(text, POSITIVE) - hits(text, NEGATIVE);
  return score > 0 ? 1 : score < 0 ? -1 : 0;
}
