// LLM boundary: a recorded-response mock for tests/offline runs, and a fetch-based Claude client.

export interface LLMClient {
  complete(system: string, prompt: string): Promise<string>;
}

export const EXTRACT_SYSTEM =
  "You extract action items and decisions from meeting notes. Return JSON only: " +
  '{"actions":[{"owner":string|null,"task":string,"due":"YYYY-MM-DD"|null,"evidence":string}],' +
  '"decisions":[{"text":string,"evidence":string}]}. owner must be one of the attendees, or null if nobody was ' +
  "named. Resolve relative dates against the meeting date. evidence must be copied verbatim from the notes. " +
  "Discussions without an outcome are neither actions nor decisions.";

/**
 * Replays responses recorded from a real model run, keyed by meeting title. Unknown meetings throw, which is
 * exactly what an outage looks like to the pipeline, so the offline demo also exercises the regex fallback.
 */
export class RecordedLLM implements LLMClient {
  constructor(private recordings: Record<string, string>) {}

  async complete(_system: string, prompt: string): Promise<string> {
    const title = /^Meeting: (.+)$/m.exec(prompt)?.[1];
    const hit = title ? this.recordings[title] : undefined;
    if (hit === undefined) throw new Error(`no recorded response for "${title}"`);
    return hit;
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
      body: JSON.stringify({ model: this.model, max_tokens: 1500, system, messages: [{ role: "user", content: prompt }] }),
    });
    if (!res.ok) throw new Error(`Anthropic API ${res.status}: ${await res.text()}`);
    const data = (await res.json()) as { content: { type: string; text?: string }[] };
    return data.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  }
}
