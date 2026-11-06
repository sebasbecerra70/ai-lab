// Turn the affinity map into an LLM-written insight summary and verify its citations.
import type { Cluster } from "./affinity.ts";
import type { LLMClient } from "./llm.ts";

export const SYSTEM = `You are a senior product researcher. Write 3-5 numbered insights from the clusters.
Each insight must state how many participants raised it and cite quote IDs in square brackets, e.g. [P2-3].
Only use quotes provided. Do not invent numbers.`;

export function buildPrompt(clusters: Cluster[], totalParticipants: number): string {
  const rows = clusters.map(
    (c) => `- ${c.theme} | ${c.participants.length} of ${totalParticipants} participants | net ${c.netSentiment} | quotes: ${c.quotes.map((q) => q.id).join(", ")}`,
  );
  const quotes = clusters.flatMap((c) => c.quotes).filter((q, i, a) => a.findIndex((x) => x.id === q.id) === i);
  return `CLUSTERS\n${rows.join("\n")}\n\nQUOTES\n${quotes.map((q) => `${q.id}: ${q.text}`).join("\n")}`;
}

export interface CitationCheck {
  cited: string[];
  unknown: string[];
  uncitedLines: number;
}

export function checkCitations(summary: string, validIds: Set<string>): CitationCheck {
  const cited = [...summary.matchAll(/\[(P\d+-\d+)\]/g)].map((m) => m[1]);
  const lines = summary.split("\n").filter((l) => /^\d+\./.test(l.trim()));
  return {
    cited: [...new Set(cited)],
    unknown: [...new Set(cited.filter((id) => !validIds.has(id)))],
    uncitedLines: lines.filter((l) => !/\[P\d+-\d+\]/.test(l)).length,
  };
}

export async function summarize(llm: LLMClient, clusters: Cluster[], totalParticipants: number) {
  const summary = await llm.complete(SYSTEM, buildPrompt(clusters, totalParticipants));
  const valid = new Set(clusters.flatMap((c) => c.quotes.map((q) => q.id)));
  return { summary, check: checkCitations(summary, valid) };
}
