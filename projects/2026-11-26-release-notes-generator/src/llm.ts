// LLM client interface: a deterministic mock for tests, and a real Anthropic client via fetch.

export interface LLMClient {
  complete(system: string, prompt: string): Promise<string>;
}

export class AnthropicLLM implements LLMClient {
  constructor(private apiKey = process.env.ANTHROPIC_API_KEY ?? "", private model = "claude-sonnet-5-5") {}

  async complete(system: string, prompt: string): Promise<string> {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "x-api-key": this.apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({ model: this.model, max_tokens: 1200, system, messages: [{ role: "user", content: prompt }] }),
    });
    if (!res.ok) throw new Error(`Anthropic API ${res.status}: ${await res.text()}`);
    const data = (await res.json()) as { content: { type: string; text?: string }[] };
    return data.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  }
}

/** Rewrites like a decent copywriter, applying the glossary from the prompt. It also "summarizes away"
 *  the numbers in performance items, a real failure mode the guard has to catch. */
export class MockLLM implements LLMClient {
  async complete(_system: string, prompt: string): Promise<string> {
    const glossary = Object.fromEntries([...prompt.matchAll(/^GLOSSARY (.+?) => (.+)$/gm)].map((m) => [m[1], m[2]]));
    const items = [...prompt.matchAll(/^(N\d+) \| (\w+) \| (.+)$/gm)];
    const out: Record<string, string> = {};
    for (const [, id, kind, raw] of items) {
      let t = raw;
      for (const [k, v] of Object.entries(glossary)) t = t.replace(new RegExp(`\\b${k}\\b`, "gi"), v);
      if (kind === "feature") t = t.replace(/^(add|introduce|support)\s+/i, "");
      if (kind === "fix") t = t.replace(/ when /, " after the ").replace(/^(.+?) drops /, "$1 no longer drops ");
      if (kind === "performance") t = "Search is now much faster for large workspaces";
      if (kind === "breaking") t = t.replace(/^replace (.+) with (.+)$/i, "$2 replaces $1");
      out[id] = t.charAt(0).toUpperCase() + t.slice(1);
    }
    return "```json\n" + JSON.stringify(out, null, 1) + "\n```";
  }
}
