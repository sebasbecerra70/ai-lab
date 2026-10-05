# Inventory MCP Server

A dependency-free [Model Context Protocol](https://modelcontextprotocol.io) server that lets any MCP-capable assistant (Claude Desktop, Claude Code, an internal agent) check stock, find low-cover positions, reserve units and rebalance between warehouses, with schema validation and guardrails on every write.

```text
$ npm run demo
> low_stock_report min_days=7
  PJ-5500@DFW available=12 cover=3.5d
  SW-18-80@DFW available=190 cover=3.5d
  GL-NIT-L@ATL available=85 cover=4.7d
  LB-4X6-1K@DFW available=150 cover=5d

> transfer_stock 400 x SW-18-80 ATL -> DFW
  from SW-18-80@ATL available=580 cover=15.3d
  to   SW-18-80@DFW available=590 cover=10.7d

> reserve_stock 25 x SC-BT-200 at ATL (too many)
  isError: only 9 available of SC-BT-200 at ATL

> reserve_stock with qty as a string (schema violation)
  isError: 'qty' must be integer

> tools/frobnicate (unknown method)
  error -32601: method not found: tools/frobnicate
```

## Why it matters
Inventory planners answer the same questions all day: "how many do we have in Dallas?", "what runs out this week?", "can we move some from Atlanta?". Each answer means a trip through the WMS. With an MCP server in front of the inventory system, an assistant can answer those questions in chat and propose a transfer. Every tool is a narrow, validated function, so the model never gets raw database access.

Scenario: stretch wrap at the Dallas DC has 3.5 days of cover, and Atlanta has 26. The assistant spots the gap, then proposes and executes a 400-unit transfer, which brings Dallas to 10.7 days. Reserved units can't be moved, so open orders are protected. At 55 rolls a day, a stockout at one DC costs about one shift of manual wrapping or delayed outbound loads. Catching it from a chat question instead of a weekly report is the whole point.

## Architecture
```
 MCP client (Claude, agent)            this server
 ──────────────────────────            ────────────────────────────────────────────
   stdin/stdout, one JSON-RPC  ──►  stdio.ts   line reader, stdout = protocol only
   message per line                     │
                                        ▼
                                    server.ts  McpServer.handle()
                                      ├─ initialize / ping / notifications
                                      ├─ tools/list, tools/call ── validateArgs(inputSchema)
                                      └─ resources/list, templates, read
                                        │
                                        ▼
                                    inventory.ts  Inventory (positions, reserve, transfer)
                                        ▲
                                    data/inventory.json  (3 DCs, 5 SKUs)
```
- **Transport-agnostic core.** `McpServer.handle()` takes one parsed message and returns one response, so it can be unit-tested without pipes. `stdio.ts` is 20 lines of glue, and an HTTP transport would be about as small.
- **Two kinds of errors.** Protocol problems (bad JSON, unknown method or tool) return JSON-RPC errors. Business problems (not enough stock, bad arguments) return `isError: true` tool results, so the model can read the message and try again with a better call, as the MCP spec recommends.
- **Schema validation before execution.** The same `inputSchema` advertised in `tools/list` is enforced on `tools/call`. Unknown arguments are rejected, so a hallucinated parameter fails loudly instead of being silently ignored.
- **Safe writes.** Transfers only move unreserved units, quantities must be positive integers, and the server works on a deep copy of the fixture. Swapping in a real WMS adapter only means replacing the `Inventory` class.
- **Initialize gate.** Methods are refused until `initialize`. That surfaces client bugs early instead of letting them half-work.
- **Trade-off:** no dependencies, so the server implements only the subset of MCP it needs (tools and resources, no prompts, sampling or subscriptions). The official SDK would add those at the cost of a dependency tree.

## Run
```bash
npm test          # 11 tests incl. an end-to-end stdio session
npm run demo      # scripted client session, printed as a transcript
npm start         # real stdio server; point an MCP client at: npx tsx src/stdio.ts
```
Claude Desktop / Claude Code config:
```json
{"mcpServers": {"inventory": {"command": "npx", "args": ["tsx", "/path/to/src/stdio.ts"]}}}
```
Set `INVENTORY_FILE` to serve a different JSON snapshot.

## Next steps
- Add an approval threshold: transfers above a dollar value return a pending ticket instead of executing.
- Write an audit log of every state-changing call, including the client name from `initialize`.
- Add a Streamable HTTP transport with auth for shared, multi-user deployment.
- Add an MCP prompt template ("weekly rebalancing review") that chains `low_stock_report` and `get_stock`.
