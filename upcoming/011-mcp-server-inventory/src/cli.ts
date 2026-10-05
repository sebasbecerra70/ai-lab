// Demo: a scripted MCP client session against the server, printed as a wire transcript.
import { readFileSync } from "node:fs";
import { Inventory, type InventoryData } from "./inventory.ts";
import { handleLine, McpServer } from "./server.ts";

const data = JSON.parse(readFileSync(new URL("../data/inventory.json", import.meta.url), "utf8")) as InventoryData;
const server = new McpServer(new Inventory(data));

let nextId = 1;
function call(method: string, params?: Record<string, unknown>, label?: string): any {
  const req = { jsonrpc: "2.0", id: nextId++, method, ...(params ? { params } : {}) };
  const res = handleLine(server, JSON.stringify(req));
  console.log(`\n> ${label ?? method}`);
  return res;
}

function show(res: any): void {
  if (res?.error) return console.log(`  error ${res.error.code}: ${res.error.message}`);
  const r = res.result;
  const out = r?.structuredContent?.result;
  const fmt = (p: any) => `${p.sku}@${p.warehouse} available=${p.available} cover=${p.daysOfCover}d`;
  if (Array.isArray(out) && out[0]?.warehouse) return out.forEach((p) => console.log(`  ${fmt(p)}`));
  if (out?.from) return console.log(`  from ${fmt(out.from)}\n  to   ${fmt(out.to)}`);
  if (r?.content) {
    const text = r.content[0].text as string;
    console.log(`  ${r.isError ? "isError: " : ""}${text.length > 300 ? `${text.slice(0, 300)}...` : text}`);
  } else console.log(`  ${JSON.stringify(r)}`);
}

const init = call("initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "demo", version: "0" } });
console.log(`  server ${init.result.serverInfo.name} ${init.result.serverInfo.version}, protocol ${init.result.protocolVersion}`);
handleLine(server, JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }));

const tools = call("tools/list").result.tools as { name: string; inputSchema: { required?: string[] } }[];
for (const t of tools) console.log(`  ${t.name}(${(t.inputSchema.required ?? []).join(", ")})`);

show(call("tools/call", { name: "low_stock_report", arguments: { min_days: 7 } }, "low_stock_report min_days=7"));
show(call("tools/call", { name: "get_stock", arguments: { sku: "SW-18-80" } }, "get_stock SW-18-80"));
show(call("tools/call", { name: "transfer_stock", arguments: { sku: "SW-18-80", from: "ATL", to: "DFW", qty: 400 } }, "transfer_stock 400 x SW-18-80 ATL -> DFW"));
show(call("tools/call", { name: "reserve_stock", arguments: { sku: "SC-BT-200", warehouse: "ATL", qty: 25 } }, "reserve_stock 25 x SC-BT-200 at ATL (too many)"));
show(call("tools/call", { name: "reserve_stock", arguments: { sku: "SC-BT-200", warehouse: "ATL", qty: "5" } }, "reserve_stock with qty as a string (schema violation)"));
const res = call("resources/read", { uri: "inventory://low-stock" }, "resources/read inventory://low-stock (after transfer)");
for (const p of JSON.parse(res.result.contents[0].text)) console.log(`  ${p.sku}@${p.warehouse} cover=${p.daysOfCover}d`);
show(call("tools/frobnicate", {}, "tools/frobnicate (unknown method)"));
