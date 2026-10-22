import { test } from "node:test";
import assert from "node:assert/strict";
import { Interview, QUESTIONS } from "./interview.ts";

const q = (id: string) => QUESTIONS.find((x) => x.id === id)!;

test("metrics without numbers trigger a follow-up naming the vague ones", () => {
  assert.match(q("goals").check("- Faster printing\n- Tickets 140 -> 40")!, /Faster printing/);
  assert.equal(q("goals").check("- p50 print time 11 min -> 2 min"), null);
});

test("problem needs both detail and evidence", () => {
  assert.match(q("problem").check("Labels are slow.")!, /25\+ words/);
  const long = "Clerks print labels one at a time which wastes a lot of time every single day across every warehouse we serve and frustrates them and their supervisors who plan waves";
  assert.match(q("problem").check(long)!, /evidence/);
  assert.equal(q("problem").check(`${long} costing 11 minutes per wave`), null);
});

test("requirements must be tagged and include a P0", () => {
  assert.match(q("requirements").check("- Print labels")!, /Tag each requirement/);
  assert.match(q("requirements").check("- P1: Print labels")!, /P0/);
  assert.equal(q("requirements").check("- P0: Print labels\n- P2: Sort"), null);
});

test("interview re-asks with the follow-up, then accepts a good answer", async () => {
  const asked: string[] = [];
  const iv = new Interview();
  const answers = await iv.run((id, prompt, attempt) => {
    asked.push(prompt);
    if (id === "goals") return attempt === 0 ? "- Better" : "- NPS 31 -> 40";
    return {
      title: "Bulk print",
      problem: "Clerks print labels one at a time which wastes a lot of time every day across every warehouse and drives 140 tickets a month to support and supervisors",
      users: "- Clerk",
      non_goals: "- Rates",
      requirements: "- P0: Print",
      risks: "- Rate limits",
      launch: "Flag to ten partners then GA after two weeks",
    }[id]!;
  });
  assert.equal(answers.goals, "- NPS 31 -> 40");
  assert.ok(asked.some((p) => p.includes("no number")));
  assert.equal(iv.transcript.filter((t) => t.followUp).length, 1);
});

test("interview gives up after max follow-ups and keeps the last answer", async () => {
  const iv = new Interview(1);
  const answers = await iv.run((id, _p, attempt) => (id === "title" ? `x${attempt}` : "- P0: something with 1 number and enough words to pass the length check for problem statements easily here ok"));
  assert.equal(answers.title, "x1");
  assert.equal(iv.transcript.filter((t) => t.questionId === "title").length, 2);
});
