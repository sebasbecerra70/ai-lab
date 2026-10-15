// stdio transport: newline-delimited JSON-RPC on stdin/stdout. Logs go to stderr so stdout stays protocol-clean.
import { readFileSync } from "node:fs";
import { createInterface } from "node:readline";
import { Inventory, type InventoryData } from "./inventory.ts";
import { handleLine, McpServer } from "./server.ts";

export function loadInventory(): Inventory {
  const path = process.env.INVENTORY_FILE ?? new URL("../data/inventory.json", import.meta.url);
  return new Inventory(JSON.parse(readFileSync(path, "utf8")) as InventoryData);
}

const server = new McpServer(loadInventory());
const rl = createInterface({ input: process.stdin });
rl.on("line", (line) => {
  if (!line.trim()) return;
  const response = handleLine(server, line);
  if (response) process.stdout.write(`${JSON.stringify(response)}\n`);
});
rl.on("close", () => process.exit(0));
process.stderr.write("inventory-mcp ready on stdio\n");
