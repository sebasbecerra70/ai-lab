# Multi-Agent Planner

Three agents (a planner, an executor and a critic) work through a shared scratchpad to answer an operational planning question with real arithmetic tools. The critic catches what the planner missed, the planner revises, and every step is logged. Offline runs use a deterministic mock LLM, so the loop is fully testable.

```text
$ python -m agent_team
TASK: We must add 120 1U servers to our data hall. How many racks do we need, can the facility power it, what does it cost, and what do you recommend?

SCRATCHPAD
[r1 planner:plan] racks_by_space -> it_load_kw -> capex_usd -> recommendation
[r1 executor:result] racks_by_space = 3
[r1 executor:result] it_load_kw = 54
[r1 executor:result] capex_usd = 1,194,000
[r1 executor:draft] Deploy all servers in 3 racks for $1,194,000.
[r1 critic:critique] rack count ignores the 12 kW rack power limit; facility power (IT load x PUE) is never checked against available power
[r2 planner:plan] racks_by_space -> it_load_kw -> racks_by_power -> racks_needed -> facility_kw -> power_shortfall_kw -> servers_now -> capex_usd -> annual_energy_usd -> recommendation
[r2 executor:result] racks_by_space = 3
[r2 executor:result] it_load_kw = 54
[r2 executor:result] racks_by_power = 5
[r2 executor:result] racks_needed = 5
[r2 executor:result] facility_kw = 75.6
[r2 executor:result] power_shortfall_kw = 35.6
[r2 executor:result] servers_now = 63
[r2 executor:result] capex_usd = 1,230,000
[r2 executor:result] annual_energy_usd = 72,848.16
[r2 executor:draft] Deploy in 5 racks (power-bound, not space-bound). Facility draw 75.6 kW exceeds the 40 kW available by 35.6 kW: phase 1 installs 63 servers now, the rest after the power upgrade. Capex $1,230,000; energy ~$72,848/year.
[r2 critic:approval] plan satisfies the task

APPROVED after 2 round(s); LLM calls {'planner': 2, 'writer': 2, 'critic': 2}, ~1006 tokens

ANSWER: Deploy in 5 racks (power-bound, not space-bound). Facility draw 75.6 kW exceeds the 40 kW available by 35.6 kW: phase 1 installs 63 servers now, the rest after the power upgrade. Capex $1,230,000; energy ~$72,848/year.
```

## Why it matters
Single-shot LLM answers to planning questions fail in a predictable way: they answer the obvious constraint and skip the binding one. In the sample, the first plan sizes the deployment by rack space (3 racks, done), which is wrong. A critic that checks against the known constraints (12 kW per rack, 40 kW of facility power) forces a revision. The correct answer is 5 racks, and power covers only 63 servers until the upgrade. A data center manager who acted on the first answer would have ordered the wrong number of racks and found the power shortfall on install day. The architecture matters as much as the answer. Numbers come from a sandboxed calculator, not from the model, and the scratchpad is an audit trail of who decided what. The loop is also bounded, so a stuck plan escalates to a human instead of burning tokens.

## Architecture
```
                ┌──────────────────── Scratchpad (shared, append-only) ─────────────────────┐
                │ [r1 planner:plan] [r1 executor:result]... [r1 critic:critique] [r2 ...]   │
                └───────▲───────────────────▲────────────────────────▲──────────────────────┘
                        │                   │                        │
 task + facts ──► Planner (LLM) ──steps──► Executor ──results──► Critic
                  JSON plan:              calc → safe_eval()     1. deterministic guard:
                  id/tool/expr            (AST whitelist)           tool errors → revise
                        ▲                 draft → writer LLM     2. LLM review → approve | revise
                        └────────────── critique ◄────────────────────────┘
                                 orchestrator: max_rounds, usage accounting
```
- **Agents communicate only through the scratchpad.** That makes the conversation inspectable and replayable, and it lets agents be swapped independently (e.g., a cheaper model for the critic).
- **Models plan; tools compute.** The executor evaluates expressions with an AST-whitelisted calculator (no `eval`, no attribute access, no imports), so arithmetic is exact and prompt injection can't reach the host.
- **Code checks before model checks.** Tool errors fail the round without spending a critic call. The LLM critic only judges completeness.
- **Bounded autonomy.** `max_rounds` plus per-role call and token accounting. Failing to converge is reported as "NOT APPROVED" for human review, never silently returned as an answer.
- **The deterministic mock is scripted by role** (planner, critic, writer), with an intentionally flawed first plan. That makes the revise path a regression test rather than a hope.

## Run
```bash
pip install pytest
python -m pytest -q                       # 14 tests, offline
python -m agent_team 120                  # mock LLM
ANTHROPIC_API_KEY=... python -m agent_team 200
```

## Next steps
- Give the critic a checklist generated from the facts schema (every limit-type fact must appear in a constraint step).
- Add an LLM-as-judge eval set of 20 planning tasks, and track how often the critic catches injected errors.
- Run executor steps in parallel when they don't depend on each other, by building a DAG from the expression variable references.
