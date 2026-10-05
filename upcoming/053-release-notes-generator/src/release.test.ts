import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { dedupe, nextVersion, parseLog, semverBump } from "./commits.ts";
import { type LLMClient, MockLLM } from "./llm.ts";
import { allItems, group, render } from "./notes.ts";
import { checkRewrite, polish } from "./polish.ts";

const log = readFileSync(new URL("../data/commits.txt", import.meta.url), "utf8");
const glossary = JSON.parse(readFileSync(new URL("../data/glossary.json", import.meta.url), "utf8"));
const commits = parseLog(log);
const { kept } = dedupe(commits);
const notes = group(kept, glossary.areas);

test("parses type, scope, breaking marker, refs and footer", () => {
  const dash = commits.find((c) => c.hash === "0b9e3f2")!;
  assert.equal(dash.type, "feat");
  assert.equal(dash.scope, "dashboard");
  assert.equal(dash.subject, "replace legacy widgets API with v2 layout engine");
  assert.ok(dash.breaking);
  assert.match(dash.breakingNote!, /must migrate to \/api\/v2\/layouts/);
  assert.deepEqual(commits.find((c) => c.hash === "5d2f7b0")!.refs, ["#420", "#398"]);
});

test("BREAKING CHANGE footer marks a commit breaking even without '!'", () => {
  const [c] = parseLog("commit abc\nfix(api): change pagination\n\nBREAKING CHANGE: cursor replaces page");
  assert.ok(c.breaking);
});

test("non-conventional commits are flagged, merges are ignored", () => {
  assert.equal(commits.filter((c) => c.type === "other").length, 2);
  assert.deepEqual(notes.unparsed.map((c) => c.subject), ["updated stuff"]);
});

test("duplicates (cherry-picks) are dropped", () => {
  const { dropped } = dedupe(commits);
  assert.deepEqual(dropped.map((c) => c.hash), ["6c0d1f9"]);
});

test("grouping hides internal work and maps scopes to product areas", () => {
  assert.equal(notes.internal, 5);
  assert.equal(notes.breaking.length, 2);
  assert.deepEqual(notes.features.map((i) => i.area), ["Billing", "Integrations"]);
  assert.equal(notes.fixes.length, 3);
  assert.equal(notes.performance[0].area, "Search");
});

test("semver bump follows conventional-commit rules", () => {
  assert.equal(semverBump(kept), "major");
  assert.equal(semverBump(kept.filter((c) => !c.breaking)), "minor");
  assert.equal(semverBump(parseLog("commit 1\nfix: x")), "patch");
  assert.equal(semverBump(parseLog("commit 1\nchore: x")), "none");
  assert.equal(nextVersion("3.7.2", "major"), "4.0.0");
  assert.equal(nextVersion("3.7.2", "minor"), "3.8.0");
});

test("rewrite guard keeps numbers honest and blocks invented refs", () => {
  assert.equal(checkRewrite("p95 from 840ms to 210ms", "Search is much faster"), "dropped number(s) 95, 840, 210");
  assert.equal(checkRewrite("faster search", "Search is 4x faster"), "introduced number(s) 4");
  assert.equal(checkRewrite("fix login", "Fixed login (#999)"), "added an issue reference");
  assert.equal(checkRewrite("fix login", "x".repeat(200)), "longer than 160 characters");
  assert.equal(checkRewrite("fix login loop", "Sign-in no longer loops"), null);
});

test("polish accepts good rewrites and keeps the original where the model lost facts", async () => {
  const p = await polish(new MockLLM(), allItems(notes), notes, glossary.jargon);
  const perf = notes.performance[0].id;
  assert.ok(!(perf in p.text));
  assert.equal(p.rejected.length, 1);
  assert.equal(p.text[notes.features[1].id], "Slack notifications for SLA breaches");
});

test("polish survives a model that invents ids or returns prose", async () => {
  const items = allItems(notes);
  const inventive: LLMClient = { complete: async () => JSON.stringify({ N1: "Dashboards got a v2 layout engine", N99: "Free pizza" }) };
  const p = await polish(inventive, items, notes, {});
  assert.ok(p.rejected.some((r) => r.id === "N99" && r.reason.includes("invented")));
  assert.ok(p.rejected.some((r) => r.id === "N2" && r.reason.includes("missing")));
  const chatty: LLMClient = { complete: async () => "Sure! Here are your notes." };
  assert.equal((await polish(chatty, items, notes, {})).rejected.length, items.length);
});

test("rendered notes include migration actions and refs", () => {
  const md = render("4.0.0", notes);
  assert.match(md, /### Breaking changes/);
  assert.match(md, /Action needed: digest send time moves/);
  assert.match(md, /\(#420, #398\)/);
  assert.ok(!md.includes("eslint"));
});
