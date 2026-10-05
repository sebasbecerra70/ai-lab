"""LLM client interface, a scripted role-aware mock, and a real Claude client via stdlib HTTP."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


V1_PLAN = {"steps": [
    {"id": "racks_by_space", "tool": "calc", "expr": "ceil(servers * server_height_u / usable_u_per_rack)"},
    {"id": "it_load_kw", "tool": "calc", "expr": "servers * server_power_kw"},
    {"id": "capex_usd", "tool": "calc", "expr": "racks_by_space * rack_cost_usd + servers * server_cost_usd"},
    {"id": "recommendation", "tool": "draft", "expr": ""},
]}

V2_PLAN = {"steps": [
    {"id": "racks_by_space", "tool": "calc", "expr": "ceil(servers * server_height_u / usable_u_per_rack)"},
    {"id": "it_load_kw", "tool": "calc", "expr": "servers * server_power_kw"},
    {"id": "racks_by_power", "tool": "calc", "expr": "ceil(it_load_kw / rack_power_limit_kw)"},
    {"id": "racks_needed", "tool": "calc", "expr": "max(racks_by_space, racks_by_power)"},
    {"id": "facility_kw", "tool": "calc", "expr": "it_load_kw * pue"},
    {"id": "power_shortfall_kw", "tool": "calc", "expr": "max(0, facility_kw - available_facility_power_kw)"},
    {"id": "servers_now", "tool": "calc", "expr": "floor(available_facility_power_kw / (server_power_kw * pue))"},
    {"id": "capex_usd", "tool": "calc", "expr": "racks_needed * rack_cost_usd + servers * server_cost_usd"},
    {"id": "annual_energy_usd", "tool": "calc", "expr": "facility_kw * 8760 * energy_cost_usd_per_kwh"},
    {"id": "recommendation", "tool": "draft", "expr": ""},
]}


class MockLLM:
    """Deterministic stand-in that plays each role from the prompt it receives.

    The first plan deliberately ignores per-rack and facility power limits, so the
    critic has something real to catch and the planner has to revise.
    """

    def complete(self, system: str, prompt: str) -> str:
        role = re.search(r"ROLE: (\w+)", system).group(1)
        if role == "planner":
            revised = "rack power limit" in prompt and "CRITIQUE" in prompt
            return json.dumps(V2_PLAN if revised else V1_PLAN)
        if role == "critic":
            results = json.loads(re.search(r"RESULTS: (\{.*\})", prompt).group(1))
            issues = []
            if "racks_by_power" not in results:
                issues.append("rack count ignores the 12 kW rack power limit")
            if "facility_kw" not in results:
                issues.append("facility power (IT load x PUE) is never checked against available power")
            return json.dumps({"verdict": "revise" if issues else "approve", "issues": issues})
        if role == "writer":
            r = json.loads(re.search(r"RESULTS: (\{.*\})", prompt).group(1))
            if "racks_by_space" not in r:
                return "Insufficient results to make a recommendation."
            if "facility_kw" not in r:
                return f"Deploy all servers in {r['racks_by_space']:.0f} racks for ${r['capex_usd']:,.0f}."
            return (f"Deploy in {r['racks_needed']:.0f} racks (power-bound, not space-bound). Facility draw "
                    f"{r['facility_kw']:.1f} kW exceeds the {r['facility_kw'] - r['power_shortfall_kw']:.0f} kW "
                    f"available by {r['power_shortfall_kw']:.1f} kW: phase 1 installs {r['servers_now']:.0f} "
                    f"servers now, the rest after the power upgrade. Capex ${r['capex_usd']:,.0f}; "
                    f"energy ~${r['annual_energy_usd']:,.0f}/year.")
        raise ValueError(f"unknown role {role}")


class AnthropicLLM:
    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({
            "model": self.model, "max_tokens": 1500, "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")


def parse_json(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError(f"no JSON object in model output: {raw[:80]!r}")
    return json.loads(m.group(0))
