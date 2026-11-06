import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { buildAffinityMap, renderAffinityMap, tagAll } from "./affinity.ts";
import { buildPrompt, checkCitations, summarize } from "./insights.ts";
import { type LLMClient, MockLLM } from "./llm.ts";
import { parseTranscripts } from "./parse.ts";
import { sentiment, tagThemes } from "./tagger.ts";

const raw = readFileSync(new URL("../data/interviews.txt", import.meta.url), "utf8");
const { participants, quotes } = parseTranscripts(raw);
const { clusters, untagged } = buildAffinityMap(tagAll(quotes), participants.length);

test("parser skips interviewer lines and numbers quotes per participant", () => {
  assert.equal(participants.length, 6);
  assert.equal(quotes.length, 30);
  assert.ok(quotes.every((q) => !q.text.startsWith("Walk me")));
  assert.deepEqual(quotes.slice(0, 2).map((q) => q.id), ["P1-1", "P1-2"]);
  assert.equal(participants[1].profile, "Director of fulfillment, mid-market retailer");
});

test("theme tagging supports multiple themes per quote", () => {
  assert.deepEqual(tagThemes("Pricing is confusing and the Shopify integration is missing"), ["Pricing & packaging", "Integrations"]);
  assert.deepEqual(tagThemes("The weather is nice"), []);
});

test("sentiment lexicon separates praise from pain", () => {
  assert.equal(sentiment("I love the alerting"), 1);
  assert.equal(sentiment("The search is slow and crashes"), -1);
  assert.equal(sentiment("We use it on Mondays"), 0);
});

test("affinity map ranks by participant reach, pain first on ties", () => {
  assert.equal(clusters[0].theme, "Pricing & packaging");
  assert.equal(clusters[0].participants.length, 5);
  for (let i = 1; i < clusters.length; i++) assert.ok(clusters[i - 1].participants.length >= clusters[i].participants.length);
  assert.ok(Math.abs(clusters[0].reach - 5 / 6) < 1e-9);
});

test("quotes with no theme are kept in an untagged bucket", () => {
  assert.deepEqual(untagged.map((q) => q.id), ["P1-2"]);
});

test("rendered map shows the most negative quotes first", () => {
  const text = renderAffinityMap(clusters.filter((c) => c.theme === "Performance"), 1);
  assert.match(text, /\[-\] Performance/);
  assert.match(text, /P3-1|P4-4|P5-5/);
});

test("prompt lists every cluster and every quote once", () => {
  const prompt = buildPrompt(clusters, 6);
  assert.equal((prompt.match(/^- /gm) ?? []).length, clusters.length);
  assert.equal((prompt.match(/^P1-1: /gm) ?? []).length, 1);
});

test("citation check flags invented quote ids and uncited lines", () => {
  const check = checkCitations("1. Real [P1-1]\n2. Fake [P9-9]\n3. No cite", new Set(["P1-1"]));
  assert.deepEqual(check.unknown, ["P9-9"]);
  assert.equal(check.uncitedLines, 1);
});

test("mock summary is grounded and fully cited", async () => {
  const { summary, check } = await summarize(new MockLLM(), clusters, 6);
  assert.equal(summary.split("\n").length, 3);
  assert.match(summary, /Pricing & packaging is a pain point for 5 of 6/);
  assert.equal(check.unknown.length, 0);
  assert.equal(check.uncitedLines, 0);
});

test("summarize surfaces hallucinated citations from a bad model", async () => {
  const bad: LLMClient = { complete: async () => "1. Users want AI features [P7-1]" };
  const { check } = await summarize(bad, clusters, 6);
  assert.deepEqual(check.unknown, ["P7-1"]);
});
