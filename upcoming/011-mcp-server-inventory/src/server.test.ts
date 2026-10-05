import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { Inventory, type InventoryData } from "./inventory.ts";
import { ERR, handleLine, McpServer, validateArgs } from "./server.ts";

const DATA = JSON.parse(readFileSync(new URL("../data/inventory.json", import.meta.url), "utf8")) as InventoryData;

function ready(): McpServer {
  const s = new McpServer(new Inventory(DATA));
  s.handle({ jsonrpc: "2.0", id: 0, method: "initialize", params: {} });
  return s;
}

const callTool = (s: McpServer, name: string, args: unknown) =>
  s.handle({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }) as any;

test("initialize advertises tools and resources capabilities", () => {
  const s = new McpServer(new Inventory(DATA));
  const r = s.handle({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} }) as any;
  assert.equal(r.result.protocolVersion, "2025-06-18");
  assert.ok(r.result.capabilities.tools && r.result.capabilities.resources);
});

test("requests before initialize are rejected; notifications get no response", () => {
  const s = new McpServer(new Inventory(DATA));
  const r = s.handle({ jsonrpc: "2.0", id: 7, method: "tools/list" }) as any;
  assert.equal(r.error.code, ERR.INVALID_REQUEST);
  assert.equal(s.handle({ jsonrpc: "2.0", method: "notifications/initialized" }), null);
});

test("tools/list exposes every tool with a JSON schema", () => {
  const r = ready().handle({ jsonrpc: "2.0", id: 2, method: "tools/list" }) as any;
  const names = r.result.tools.map((t: any) => t.name);
  assert.deepEqual(names, ["get_stock", "search_skus", "low_stock_report", "reserve_stock", "transfer_stock"]);
  for (const t of r.result.tools) assert.equal(t.inputSchema.type, "object");
});

test("get_stock computes available units and days of cover", () => {
  const r = callTool(ready(), "get_stock", { sku: "SW-18-80", warehouse: "DFW" });
  assert.deepEqual(r.result.structuredContent.result, { sku: "SW-18-80", warehouse: "DFW", onHand: 310, reserved: 120, available: 190, daysOfCover: 3.5 });
});

test("low_stock_report is sorted most urgent first", () => {
  const out = callTool(ready(), "low_stock_report", { min_days: 7 }).result.structuredContent.result;
  const days = out.map((p: any) => p.daysOfCover);
  assert.deepEqual(days, [...days].sort((a: number, b: number) => a - b));
  assert.ok(out.every((p: any) => p.daysOfCover < 7));
  assert.equal(out[0].daysOfCover, 3.5);
  assert.equal(out.length, 4);
});

test("transfer moves only unreserved units and does not touch the fixture", () => {
  const s = ready();
  const r = callTool(s, "transfer_stock", { sku: "PJ-5500", from: "DFW", to: "ATL", qty: 12 }).result.structuredContent.result;
  assert.equal(r.from.onHand, 6);
  assert.equal(r.to.onHand, 53);
  const tooMany = callTool(s, "transfer_stock", { sku: "PJ-5500", from: "DFW", to: "ATL", qty: 1 });
  assert.equal(tooMany.result.isError, true); // remaining 6 on hand are all reserved
  assert.equal(DATA.stock.find((x) => x.sku === "PJ-5500" && x.warehouse === "DFW")!.onHand, 18);
});

test("business errors come back as isError results, not protocol errors", () => {
  const r = callTool(ready(), "reserve_stock", { sku: "SC-BT-200", warehouse: "ATL", qty: 25 });
  assert.equal(r.error, undefined);
  assert.equal(r.result.isError, true);
  assert.match(r.result.content[0].text, /only 9 available/);
});

test("validateArgs catches missing, unknown, mistyped and out-of-range arguments", () => {
  const schema = { type: "object" as const, properties: { sku: { type: "string" }, qty: { type: "integer", minimum: 1 } }, required: ["sku", "qty"] };
  assert.deepEqual(validateArgs(schema, { sku: "A", qty: 2 }), []);
  assert.deepEqual(validateArgs(schema, { qty: 1.5, color: "red" }), ["missing required argument 'sku'", "'qty' must be integer", "unknown argument 'color'"]);
  assert.deepEqual(validateArgs(schema, { sku: "A", qty: 0 }), ["'qty' must be >= 1"]);
  assert.deepEqual(validateArgs(schema, [1]), ["arguments must be an object"]);
});

test("protocol errors: parse error, unknown method, unknown tool, unknown resource", () => {
  const s = ready();
  assert.equal(handleLine(s, "{not json")!.error!.code, ERR.PARSE);
  assert.equal((s.handle({ jsonrpc: "2.0", id: 3, method: "nope" }) as any).error.code, ERR.METHOD_NOT_FOUND);
  assert.equal(callTool(s, "drop_tables", {}).error.code, ERR.INVALID_PARAMS);
  assert.equal((s.handle({ jsonrpc: "2.0", id: 4, method: "resources/read", params: { uri: "inventory://nope" } }) as any).error.code, ERR.INVALID_PARAMS);
});

test("resources/read returns JSON for a SKU template URI", () => {
  const r = ready().handle({ jsonrpc: "2.0", id: 5, method: "resources/read", params: { uri: "inventory://sku/GL-NIT-L" } }) as any;
  const body = JSON.parse(r.result.contents[0].text);
  assert.equal(body.sku.name, "Nitrile gloves L (100)");
  assert.equal(body.positions.length, 3);
});

test("stdio transport answers newline-delimited JSON-RPC end to end", async () => {
  const entry = fileURLToPath(new URL("./stdio.ts", import.meta.url));
  // Reuse the current loader flags (tsx) so the child can run TypeScript.
  const child = spawn(process.execPath, [...process.execArgv.filter((a) => !a.startsWith("--test")), entry], { stdio: ["pipe", "pipe", "pipe"] });
  const lines: string[] = [];
  let buf = "";
  child.stdout.on("data", (d) => {
    buf += d;
    const parts = buf.split("\n");
    buf = parts.pop()!;
    lines.push(...parts);
  });
  child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} })}\n`);
  child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" })}\n`);
  child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "search_skus", arguments: { query: "gloves" } } })}\n`);
  child.stdin.end();
  await new Promise((resolve) => child.on("close", resolve));
  const responses = lines.map((l) => JSON.parse(l));
  assert.deepEqual(responses.map((r) => r.id), [1, 2]);
  assert.deepEqual(responses[1].result.structuredContent.result, [{ sku: "GL-NIT-L", name: "Nitrile gloves L (100)" }]);
});
