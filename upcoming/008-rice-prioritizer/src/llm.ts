// LLM boundary: a deterministic template writer for tests/offline, and a fetch-based Claude client.

export interface LLMClient {
  complete(system: string, prompt: string): Promise<string>;
}

export const RATIONALE_SYSTEM =
  "You are a product manager writing roadmap rationale for executives. Using ONLY the numbers given, write " +
  "one or two sentences per item: why it is in this quarter, and the main risk. No new facts.";

export interface RationaleInput {
  id: string;
  name: string;
  quarter: number;
  score: number;
  rank: number;
  pTopN: number;
  verdict: string;
  notes?: string;
}

/** Offline stand-in: reads the JSON facts back out of the prompt and fills a template. */
export class TemplateLLM implements LLMClient {
  async complete(_system: string, prompt: string): Promise<string> {
    const items: RationaleInput[] = JSON.parse(prompt.slice(prompt.indexOf("[")));
    return items
      .map((i) => {
        const risk =
          i.verdict === "contested"
            ? `ranking is sensitive to estimates (top-N in ${Math.round(i.pTopN * 100)}% of simulations), so validate reach/effort first`
            : i.verdict === "robust out"
              ? "low odds of being a top item; keep scope small"
              : "ranking holds under estimate uncertainty";
        return `- Q${i.quarter} ${i.name}: RICE ${Math.round(i.score)} (#${i.rank})${i.notes ? `; ${i.notes}` : ""}. Risk: ${risk}.`;
      })
      .join("\n");
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
      body: JSON.stringify({ model: this.model, max_tokens: 800, system, messages: [{ role: "user", content: prompt }] }),
    });
    if (!res.ok) throw new Error(`Anthropic API ${res.status}: ${await res.text()}`);
    const data = (await res.json()) as { content: { type: string; text?: string }[] };
    return data.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  }
}

export async function writeRationale(llm: LLMClient, items: RationaleInput[]): Promise<string> {
  return llm.complete(RATIONALE_SYSTEM, `Roadmap items as JSON:\n${JSON.stringify(items, null, 1)}`);
}
