// MCP server core: JSON-RPC 2.0 dispatch for initialize, tools/*, resources/* and ping.
// Transport-agnostic: handle() takes one parsed message and returns a response (or null for notifications).
import { Inventory, InventoryError } from "./inventory.ts";

export const PROTOCOL_VERSION = "2025-06-18";

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: string | number | null;
  method: string;
  params?: Record<string, unknown>;
}

export interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: string | number | null;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

export const ERR = { PARSE: -32700, INVALID_REQUEST: -32600, METHOD_NOT_FOUND: -32601, INVALID_PARAMS: -32602, INTERNAL: -32603 };

type Schema = { type: "object"; properties: Record<string, { type: string; description?: string; minimum?: number }>; required?: string[] };

interface ToolDef {
  name: string;
  description: string;
  inputSchema: Schema;
  run: (inv: Inventory, args: Record<string, any>) => unknown;
}

const TOOLS: ToolDef[] = [
  {
    name: "get_stock",
    description: "Stock position (on hand, reserved, available, days of cover) for a SKU, optionally at one warehouse.",
    inputSchema: { type: "object", properties: { sku: { type: "string" }, warehouse: { type: "string" } }, required: ["sku"] },
    run: (inv, a) => (a.warehouse ? inv.position(a.sku, a.warehouse) : inv.positions(a.sku)),
  },
  {
    name: "search_skus",
    description: "Find SKUs whose code or name contains all query words.",
    inputSchema: { type: "object", properties: { query: { type: "string" } }, required: ["query"] },
    run: (inv, a) => inv.search(a.query).map((s) => ({ sku: s.sku, name: s.name })),
  },
  {
    name: "low_stock_report",
    description: "Positions with fewer than min_days of cover, most urgent first.",
    inputSchema: { type: "object", properties: { min_days: { type: "number", minimum: 0 } }, required: ["min_days"] },
    run: (inv, a) => inv.lowStock(a.min_days),
  },
  {
    name: "reserve_stock",
    description: "Reserve available units of a SKU at a warehouse for an order. Fails if not enough is available.",
    inputSchema: {
      type: "object",
      properties: { sku: { type: "string" }, warehouse: { type: "string" }, qty: { type: "integer", minimum: 1 } },
      required: ["sku", "warehouse", "qty"],
    },
    run: (inv, a) => inv.reserve(a.sku, a.warehouse, a.qty),
  },
  {
    name: "transfer_stock",
    description: "Move available (unreserved) units of a SKU between warehouses.",
    inputSchema: {
      type: "object",
      properties: { sku: { type: "string" }, from: { type: "string" }, to: { type: "string" }, qty: { type: "integer", minimum: 1 } },
      required: ["sku", "from", "to", "qty"],
    },
    run: (inv, a) => inv.transfer(a.sku, a.from, a.to, a.qty),
  },
];

export function validateArgs(schema: Schema, args: unknown): string[] {
  if (typeof args !== "object" || args === null || Array.isArray(args)) return ["arguments must be an object"];
  const a = args as Record<string, unknown>;
  const errors: string[] = [];
  for (const k of schema.required ?? []) if (!(k in a)) errors.push(`missing required argument '${k}'`);
  for (const [k, v] of Object.entries(a)) {
    const prop = schema.properties[k];
    if (!prop) {
      errors.push(`unknown argument '${k}'`);
      continue;
    }
    const ok = prop.type === "integer" ? Number.isInteger(v) : prop.type === "number" ? typeof v === "number" && Number.isFinite(v) : typeof v === prop.type;
    if (!ok) errors.push(`'${k}' must be ${prop.type}`);
    else if (prop.minimum !== undefined && (v as number) < prop.minimum) errors.push(`'${k}' must be >= ${prop.minimum}`);
  }
  return errors;
}

export class McpServer {
  private initialized = false;

  constructor(private inv: Inventory, private info = { name: "inventory-mcp", version: "1.0.0" }) {}

  handle(msg: unknown): JsonRpcResponse | null {
    if (typeof msg !== "object" || msg === null || (msg as any).jsonrpc !== "2.0" || typeof (msg as any).method !== "string") {
      return this.error((msg as any)?.id ?? null, ERR.INVALID_REQUEST, "invalid JSON-RPC 2.0 request");
    }
    const req = msg as JsonRpcRequest;
    const isNotification = !("id" in req);
    try {
      const result = this.dispatch(req);
      return isNotification ? null : { jsonrpc: "2.0", id: req.id ?? null, result };
    } catch (e) {
      if (isNotification) return null;
      if (e instanceof RpcError) return this.error(req.id ?? null, e.code, e.message);
      return this.error(req.id ?? null, ERR.INTERNAL, (e as Error).message);
    }
  }

  private error(id: string | number | null, code: number, message: string): JsonRpcResponse {
    return { jsonrpc: "2.0", id, error: { code, message } };
  }

  private dispatch(req: JsonRpcRequest): unknown {
    const p = req.params ?? {};
    switch (req.method) {
      case "initialize":
        this.initialized = true;
        return {
          protocolVersion: PROTOCOL_VERSION,
          capabilities: { tools: { listChanged: false }, resources: { listChanged: false } },
          serverInfo: this.info,
          instructions: "Inventory tools for three DCs. Reads are safe; reserve_stock and transfer_stock change state.",
        };
      case "notifications/initialized":
        return {};
      case "ping":
        return {};
    }
    // Clients must initialize first; answering earlier hides client bugs.
    if (!this.initialized) throw new RpcError(ERR.INVALID_REQUEST, "server not initialized");
    switch (req.method) {
      case "tools/list":
        return { tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })) };
      case "tools/call":
        return this.callTool(String(p.name ?? ""), p.arguments ?? {});
      case "resources/list":
        return {
          resources: [
            { uri: "inventory://warehouses", name: "Warehouses", mimeType: "application/json" },
            { uri: "inventory://low-stock", name: "Positions under 14 days of cover", mimeType: "application/json" },
          ],
        };
      case "resources/templates/list":
        return { resourceTemplates: [{ uriTemplate: "inventory://sku/{sku}", name: "Stock positions for one SKU", mimeType: "application/json" }] };
      case "resources/read":
        return { contents: [{ uri: String(p.uri), mimeType: "application/json", text: JSON.stringify(this.readResource(String(p.uri ?? ""))) }] };
      default:
        throw new RpcError(ERR.METHOD_NOT_FOUND, `method not found: ${req.method}`);
    }
  }

  private callTool(name: string, args: unknown) {
    const tool = TOOLS.find((t) => t.name === name);
    if (!tool) throw new RpcError(ERR.INVALID_PARAMS, `unknown tool: ${name}`);
    const errors = validateArgs(tool.inputSchema, args);
    // Business errors go back as isError results so the model can read them and adjust; protocol errors don't.
    if (errors.length) return { content: [{ type: "text", text: errors.join("; ") }], isError: true };
    try {
      const out = tool.run(this.inv, args as Record<string, any>);
      return { content: [{ type: "text", text: JSON.stringify(out) }], structuredContent: { result: out } };
    } catch (e) {
      if (e instanceof InventoryError) return { content: [{ type: "text", text: e.message }], isError: true };
      throw e;
    }
  }

  private readResource(uri: string): unknown {
    if (uri === "inventory://warehouses") return this.inv.warehouses;
    if (uri === "inventory://low-stock") return this.inv.lowStock(14);
    const m = uri.match(/^inventory:\/\/sku\/([A-Za-z0-9-]+)$/);
    if (m) {
      try {
        return { sku: this.inv.sku(m[1]), positions: this.inv.positions(m[1]) };
      } catch (e) {
        throw new RpcError(ERR.INVALID_PARAMS, (e as Error).message);
      }
    }
    throw new RpcError(ERR.INVALID_PARAMS, `unknown resource: ${uri}`);
  }
}

export class RpcError extends Error {
  constructor(public code: number, message: string) {
    super(message);
  }
}

/** Parse one line from the wire. Malformed JSON gets a -32700 response with a null id, per the spec. */
export function handleLine(server: McpServer, line: string): JsonRpcResponse | null {
  let msg: unknown;
  try {
    msg = JSON.parse(line);
  } catch {
    return { jsonrpc: "2.0", id: null, error: { code: ERR.PARSE, message: "parse error" } };
  }
  return server.handle(msg);
}
