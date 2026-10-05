# Tool-Calling Ops Agent

An agent loop that answers data center operations questions by **calling tools instead of guessing numbers**: a safe calculator, a site-metrics lookup and a unit converter, with JSON-schema validation and a max-steps guard.

```text
$ python -m tool_agent
Q: What is hall_b.it_load_kw in BTU per hour?
  step 1: lookup({"key": "hall_b.it_load_kw"}) -> {"key": "hall_b.it_load_kw", "value": 1215}
  step 2: convert_units({"value": 1215, "from_unit": "kW", "to_unit": "BTU/h"}) -> 4145752.0867
  answer: Answer: 4145752.0867 (from 2 tool call(s)).
Q: How much headroom is left: hall_a.it_load_kw vs hall_a.design_capacity_kw?
  step 1: lookup({"key": "hall_a.it_load_kw"}) -> {"key": "hall_a.it_load_kw", "value": 1840}
  step 2: lookup({"key": "hall_a.design_capacity_kw"}) -> {"key": "hall_a.design_capacity_kw", "value": 2400}
  step 3: calculator({"expression": "2400 - 1840"}) -> 560
  answer: Answer: 560 (from 3 tool call(s)).
Q: Generator runtime in hours = site.diesel_tank_liters / site.generator_burn_lph
  step 1: lookup({"key": "site.diesel_tank_liters"}) -> {"key": "site.diesel_tank_liters", "value": 60000}
  step 2: lookup({"key": "site.generator_burn_lph"}) -> {"key": "site.generator_burn_lph", "value": 410}
  step 3: calculator({"expression": "60000 / 410"}) -> 146.341463
  answer: Answer: 146.341463 (from 3 tool call(s)).
```

## Why it matters
An on-call engineer asking "how many hours of diesel do we have?" needs the real number from the site's records, not a plausible guess. A model doing arithmetic in its head gets this wrong often enough to matter. Getting it wrong by 20% on a 146-hour generator runtime means fuel gets reordered a day late. Here every number comes from a lookup or a deterministic calculator, and the trace shows the steps, so an operator can check the answer in seconds before acting on it.

## Architecture
```
question ─► Agent.run ──► ChatLLM.chat(system, messages, tool specs)
               ▲                 │
               │        tool_use blocks? ──no──► final answer
               │                 │yes
               │      ToolRegistry.dispatch(name, args)
               │        ├─ schema validation (required / types / unknown keys)
               │        ├─ calculator (AST whitelist, no eval)
               │        ├─ lookup (data/ops_facts.json)
               │        └─ convert_units (SI base per dimension)
               └── tool_result blocks (is_error on failure) ◄┘
                   loop until answer or max_steps guard
```
- **Messages API shapes everywhere.** Tool specs, `tool_use` and `tool_result` blocks use the Anthropic wire format, so the real client is a thin `urllib` call and needs no translation layer.
- **Errors go back to the model as data.** A bad key or a wrong type comes back as an `is_error` tool result with a hint (e.g. similar keys), so the model can retry instead of the loop crashing. A test covers that recovery path.
- **Max-steps guard.** A model stuck calling tools in a loop is stopped after `max_steps` and the result is flagged, which caps token spend.
- **The calculator never calls `eval`.** It walks a whitelisted AST and limits exponents, because tool inputs come from the model and could be influenced by injected text.
- **Two mocks.** `ScriptedLLM` replays exact turns so tests can check the loop's message bookkeeping. `KeywordPlannerLLM` is a small deterministic planner so the CLI demo runs offline.

## Run
```bash
pip install pytest
python -m pytest -q                       # 14 tests, offline
python -m tool_agent                      # demo questions
python -m tool_agent "What is hall_a.it_load_kw in tons?"
ANTHROPIC_API_KEY=... python -m tool_agent "How many hours of diesel at current burn?"
```

## Next steps
- Add parallel tool execution for independent lookups, and a per-tool timeout.
- Log traces as JSONL and replay them as regression tests against new models.
- Back `lookup` with a live DCIM/BMS API instead of the JSON fixture.
