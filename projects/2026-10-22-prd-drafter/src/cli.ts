// Demo: scripted interview -> PRD draft -> completeness check, then the checker on a weak PRD for contrast.
import { readFileSync } from "node:fs";
import { checkPrd, type CheckResult } from "./checker.ts";
import { Interview } from "./interview.ts";
import { AnthropicLLM, draftPrd, TemplateLLM } from "./llm.ts";

const scripted: Record<string, string[]> = JSON.parse(readFileSync(new URL("../data/answers.json", import.meta.url), "utf8"));

function printCheck(name: string, r: CheckResult): void {
  console.log(`\n${name}: completeness ${r.score}/100, ${r.gaps.length} gap(s)`);
  for (const g of r.gaps) console.log(`  [${g.severity}] ${g.section}: ${g.message}`);
}

const interview = new Interview();
const answers = await interview.run((id, _prompt, attempt) => {
  const options = scripted[id] ?? [""];
  return options[Math.min(attempt, options.length - 1)];
});

console.log("interview:");
for (const t of interview.transcript) {
  const short = t.answer.split("\n")[0];
  console.log(`  Q(${t.questionId}): ${t.asked}`);
  console.log(`  A: ${short.length > 90 ? `${short.slice(0, 90)}...` : short}${t.answer.includes("\n") ? " (+more)" : ""}`);
  if (t.followUp) console.log(`  -> follow-up needed`);
}

const llm = process.env.ANTHROPIC_API_KEY ? new AnthropicLLM() : new TemplateLLM();
const prd = await draftPrd(llm, answers);
console.log(`\n----- PRD (${llm.constructor.name}) -----\n${prd}\n-----`);
printCheck("drafted PRD", checkPrd(prd));
printCheck("data/weak-prd.md", checkPrd(readFileSync(new URL("../data/weak-prd.md", import.meta.url), "utf8")));
