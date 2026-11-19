// LLM client interface: a scripted mock that makes realistic mistakes, and a real Anthropic client via fetch.

export interface LLMClient {
  complete(system: string, prompt: string): Promise<string>;
}

export class AnthropicLLM implements LLMClient {
  constructor(private apiKey = process.env.ANTHROPIC_API_KEY ?? "", private model = "claude-sonnet-5-5") {}

  async complete(system: string, prompt: string): Promise<string> {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "x-api-key": this.apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({ model: this.model, max_tokens: 1000, system, messages: [{ role: "user", content: prompt }] }),
    });
    if (!res.ok) throw new Error(`Anthropic API ${res.status}: ${await res.text()}`);
    const data = (await res.json()) as { content: { type: string; text?: string }[] };
    return data.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  }
}

const line = (sku: string, qty: number | string, unit_price: number | string) => ({ sku, qty, unit_price });

// Per email, the outputs for attempt 1, 2, 3... Each first attempt reproduces a failure mode seen in practice.
const SCRIPT: Record<string, string[]> = {
  // prose + code fence + a formatted number string: all fixable locally
  e1: [
    "Here is the extracted order:\n```json\n" +
      JSON.stringify({ po_number: "PO-10421", customer: "Brightline Retail", currency: "USD", requested_date: "2026-11-14", priority: "standard",
        contact_email: "dana@brightline.example", lines: [line("CAB-210", 40, 12.5), line("RCK-1200", 10, "1,850")] }, null, 1) + "\n```",
  ],
  // missing currency, invented key, enum casing: casing is local, the rest needs a re-ask
  e2: [
    JSON.stringify({ po_number: "PO-10422", customer: "Northwind Labs", requested_date: "2026-10-30", priority: "Expedite",
      contact: "ops@northwind.example", lines: [line("SRV-880", 5, 9400)] }),
    JSON.stringify({ po_number: "PO-10422", customer: "Northwind Labs", currency: "USD", requested_date: "2026-10-30", priority: "expedite",
      contact_email: "ops@northwind.example", lines: [line("SRV-880", 5, 9400)] }),
  ],
  // trailing commas and single quotes: syntax repair
  e3: [
    "{'po_number': 'PO-10423', 'customer': 'Cobalt Foods GmbH', 'currency': 'EUR', 'requested_date': '2026-12-01', 'priority': 'standard', " +
      "'lines': [{'sku': 'PSU-450', 'qty': 200, 'unit_price': 89.0}, {'sku': 'FAN-120', 'qty': 200, 'unit_price': 14.2},],}",
  ],
  // SKU missing its dash: a judgment call, so re-ask with the pattern error
  e4: [
    JSON.stringify({ po_number: "PO-10424", customer: "Harbor Clinics", currency: "USD", requested_date: "2026-10-22", priority: "expedite",
      lines: [line("SWT480", 12, 2310)] }),
    JSON.stringify({ po_number: "PO-10424", customer: "Harbor Clinics", currency: "USD", requested_date: "2026-10-22", priority: "expedite",
      lines: [line("SWT-480", 12, 2310)] }),
  ],
  // clean on the first try
  e5: [
    JSON.stringify({ po_number: "PO-10425", customer: "Granite Supply", currency: "GBP", requested_date: "2026-11-03", priority: "standard",
      contact_email: "j.ellis@granite.example", lines: [line("UPS-3000", 1, 4100)] }),
  ],
  // the email genuinely lacks a date and priority; the model keeps guessing, so the loop must give up
  e6: [
    JSON.stringify({ po_number: "PO-10426", customer: "Lotus Electronics", currency: "USD", requested_date: "end of month",
      lines: [line("CAB-210", 30, 12.5)] }),
    JSON.stringify({ po_number: "PO-10426", customer: "Lotus Electronics", currency: "USD", requested_date: "end of month", priority: "normal",
      lines: [line("CAB-210", 30, 12.5)] }),
    JSON.stringify({ po_number: "PO-10426", customer: "Lotus Electronics", currency: "USD", requested_date: "EOM", priority: "standard",
      lines: [line("CAB-210", 30, 12.5)] }),
  ],
};

export class MockLLM implements LLMClient {
  calls = 0;

  async complete(_system: string, prompt: string): Promise<string> {
    this.calls++;
    const id = prompt.match(/^ID: (\w+)$/m)?.[1] ?? "";
    const attempt = Number(prompt.match(/^ATTEMPT: (\d+)$/m)?.[1] ?? "1");
    const script = SCRIPT[id];
    if (!script) return "Sorry, I couldn't find an order in that email.";
    return script[Math.min(attempt, script.length) - 1];
  }
}
