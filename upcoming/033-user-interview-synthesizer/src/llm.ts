// LLM client interface: deterministic mock for tests, real Anthropic client via fetch.

export interface LLMClient {
  complete(system: string, prompt: string): Promise<string>;
}

export class AnthropicLLM implements LLMClient {
  constructor(private apiKey = process.env.ANTHROPIC_API_KEY ?? "", private model = "claude-sonnet-5-5") {}

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

/** Builds insights from the CLUSTERS block of the prompt so offline output is meaningful. */
export class MockLLM implements LLMClient {
  async complete(_system: string, prompt: string): Promise<string> {
    const rows = [...prompt.matchAll(/^- (.+?) \| (\d+) of (\d+) participants \| net (-?\d+) \| quotes: (.+)$/gm)];
    return rows
      .slice(0, 3)
      .map(([, theme, n, total, net, ids], i) => {
        const tone = Number(net) < 0 ? "a pain point" : "a strength";
        const cite = ids.split(", ").slice(0, 2).map((id) => `[${id}]`).join(" ");
        return `${i + 1}. ${theme} is ${tone} for ${n} of ${total} participants. ${cite}`;
      })
      .join("\n");
  }
}
