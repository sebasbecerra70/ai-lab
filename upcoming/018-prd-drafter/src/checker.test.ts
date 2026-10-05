import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { checkPrd, parseSections, REQUIRED_SECTIONS } from "./checker.ts";

const full = (overrides: Record<string, string> = {}) => {
  const body: Record<string, string> = {
    Problem: "Clerks print labels one at a time. At peak this costs 11 minutes per 50-order wave and drives 140 tickets a month, which is 18% of all support volume for mid-size warehouses.",
    Users: "- Shipping clerk",
    "Goals and success metrics": "- Wave print time 11 min -> 2 min",
    "Non-goals": "- Rate shopping",
    Requirements: "- P0: Print 200 labels as one PDF in under 30 seconds",
    "Acceptance criteria": "- [ ] Given 200 selected orders, when the clerk clicks Print, then one PDF downloads within 30 seconds",
    "Risks and open questions": "- Carrier rate limits",
    "Launch plan": "Flag to 10 partners, then 25%, then GA.",
    ...overrides,
  };
  return `# PRD: Bulk print\n\n${REQUIRED_SECTIONS.map((s) => `## ${s}\n${body[s]}`).join("\n\n")}`;
};

test("parseSections splits on level-2 headings", () => {
  const s = parseSections("# T\n## A\none\n\n## B\ntwo\nthree");
  assert.deepEqual([...s.entries()], [["A", "one"], ["B", "two\nthree"]]);
});

test("a complete PRD scores 100", () => {
  assert.deepEqual(checkPrd(full()), { score: 100, gaps: [] });
});

test("missing and empty sections are blockers", () => {
  const md = full().replace(/## Non-goals\n- Rate shopping/, "").replace("- Shipping clerk", "");
  const r = checkPrd(md);
  assert.deepEqual(r.gaps.filter((g) => g.severity === "blocker").map((g) => `${g.section}: ${g.message}`), ["Users: section is empty", "Non-goals: section is missing"]);
  assert.equal(r.score, 60);
});

test("unmeasurable goals and vague requirements are flagged", () => {
  const r = checkPrd(full({ "Goals and success metrics": "- Happier users", Requirements: "- P0: Make printing seamless" }));
  const msgs = r.gaps.map((g) => g.message);
  assert.ok(msgs.includes('not measurable: "Happier users"'));
  assert.ok(msgs.some((m) => m.startsWith('vague word "seamless"')));
});

test("each P0 needs a Given/When/Then criterion", () => {
  const r = checkPrd(full({ Requirements: "- P0: Print labels in 30 seconds\n- P0: Show failures" }));
  assert.ok(r.gaps.some((g) => g.message === "1 Given/When/Then criteria for 2 P0 requirements"));
});

test("placeholders are caught anywhere", () => {
  const r = checkPrd(full({ "Launch plan": "TBD" }));
  assert.ok(r.gaps.some((g) => g.section === "Launch plan" && g.message.includes("TBD")));
});

test("the sample weak PRD fails hard", () => {
  const r = checkPrd(readFileSync(new URL("../data/weak-prd.md", import.meta.url), "utf8"));
  assert.equal(r.score, 0);
  assert.equal(r.gaps.filter((g) => g.severity === "blocker").length, 3);
});
