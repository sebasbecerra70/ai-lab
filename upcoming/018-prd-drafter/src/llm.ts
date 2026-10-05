// LLM boundary: a deterministic template filler for tests/offline, and a fetch-based Claude client.
import { QUESTIONS, splitList, type Answers } from "./interview.ts";

export interface LLMClient {
  complete(system: string, prompt: string): Promise<string>;
}

/** Offline stand-in: reads the answers JSON back out of the prompt and fills the PRD template verbatim. */
export class TemplateLLM implements LLMClient {
  async complete(_system: string, prompt: string): Promise<string> {
    const a: Answers = JSON.parse(prompt.slice(prompt.indexOf("{")));
    const list = (id: string) => splitList(a[id] ?? "").map((x) => `- ${x}`).join("\n");
    const reqs = splitList(a.requirements ?? "");
    const acceptance = reqs
      .filter((r) => r.startsWith("P0"))
      .map((r) => `- [ ] Given a ${splitList(a.users ?? "user")[0]?.toLowerCase() ?? "user"}, when they use "${r.replace(/^P0:?\s*/, "")}", then it works as specified`)
      .join("\n");
    return [
      `# PRD: ${a.title}`,
      "",
      "## Problem",
      a.problem,
      "",
      "## Users",
      list("users"),
      "",
      "## Goals and success metrics",
      list("goals"),
      "",
      "## Non-goals",
      list("non_goals"),
      "",
      "## Requirements",
      reqs.map((r) => `- ${r}`).join("\n"),
      "",
      "## Acceptance criteria",
      acceptance || "TBD",
      "",
      "## Risks and open questions",
      list("risks"),
      "",
      "## Launch plan",
      a.launch,
    ].join("\n");
  }
}

export class AnthropicLLM implements LLMClient {
  constructor(
    private apiKey = process.env.ANTHROPIC_API_KEY ?? "",
    private model = "claude-sonnet-5-5",
  ) {}

  async complete(system: string, prompt: string): Promise<string> {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "x-api-key": this.apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({ model: this.model, max_tokens: 2000, system, messages: [{ role: "user", content: prompt }] }),
    });
    if (!res.ok) throw new Error(`Anthropic API ${res.status}: ${await res.text()}`);
    const data = (await res.json()) as { content: { type: string; text?: string }[] };
    return data.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  }
}

export const PRD_SYSTEM =
  "You are a senior product manager. Turn the interview answers into a PRD in Markdown with exactly these sections: " +
  `${QUESTIONS.map((q) => q.section).filter((s) => s !== "Overview").join(", ")}, plus "Acceptance criteria" after Requirements. ` +
  "Start with '# PRD: <title>'. Use only the facts in the answers; do not invent metrics, dates or customers. Keep every number " +
  "the PM gave. Write acceptance criteria as '- [ ] Given ..., when ..., then ...' for each P0 requirement. " +
  "If something is missing, write it under Risks and open questions instead of making it up.";

export async function draftPrd(llm: LLMClient, answers: Answers): Promise<string> {
  return llm.complete(PRD_SYSTEM, `Interview answers as JSON:\n${JSON.stringify(answers, null, 1)}`);
}
