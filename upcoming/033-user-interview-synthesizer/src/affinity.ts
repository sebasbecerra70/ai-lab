// Group tagged quotes into an affinity map ranked by participant reach.
import type { Quote } from "./parse.ts";
import { CODEBOOK, type Sentiment, type Theme, sentiment, tagThemes } from "./tagger.ts";

export interface TaggedQuote extends Quote {
  themes: string[];
  sentiment: Sentiment;
}

export interface Cluster {
  theme: string;
  participants: string[];
  quotes: TaggedQuote[];
  netSentiment: number; // positives minus negatives
  reach: number; // share of all participants who raised it
}

export function tagAll(quotes: Quote[], codebook: Theme[] = CODEBOOK): TaggedQuote[] {
  return quotes.map((q) => ({ ...q, themes: tagThemes(q.text, codebook), sentiment: sentiment(q.text) }));
}

export function buildAffinityMap(tagged: TaggedQuote[], totalParticipants: number): { clusters: Cluster[]; untagged: TaggedQuote[] } {
  const byTheme = new Map<string, TaggedQuote[]>();
  const untagged: TaggedQuote[] = [];
  for (const q of tagged) {
    if (q.themes.length === 0) untagged.push(q);
    for (const t of q.themes) byTheme.set(t, [...(byTheme.get(t) ?? []), q]);
  }
  const clusters = [...byTheme.entries()].map(([theme, quotes]) => {
    const participants = [...new Set(quotes.map((q) => q.participant))].sort();
    return {
      theme,
      participants,
      quotes,
      netSentiment: quotes.reduce((s, q) => s + q.sentiment, 0),
      reach: participants.length / totalParticipants,
    };
  });
  // Rank by how many people raised it, then by how negative it is (pain first).
  clusters.sort((a, b) => b.participants.length - a.participants.length || a.netSentiment - b.netSentiment || a.theme.localeCompare(b.theme));
  return { clusters, untagged };
}

export function renderAffinityMap(clusters: Cluster[], maxQuotes = 2): string {
  const lines: string[] = [];
  for (const c of clusters) {
    const mood = c.netSentiment > 0 ? "+" : c.netSentiment < 0 ? "-" : "~";
    lines.push(`[${mood}] ${c.theme}  (${c.participants.length} participants: ${c.participants.join(", ")}; net ${c.netSentiment})`);
    const ordered = [...c.quotes].sort((a, b) => a.sentiment - b.sentiment);
    for (const q of ordered.slice(0, maxQuotes)) lines.push(`      ${q.id}: "${q.text}"`);
  }
  return lines.join("\n");
}
