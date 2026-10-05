"""LLM client interface: a template mock for offline runs and tests, and a real Claude client via stdlib HTTP."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class MockLLM:
    """Writes an executive summary from FACTS. With `sloppy`, the first draft makes two classic mistakes
    (rounds the revenue gap wrong and says a lower-is-better metric 'beat plan' when it rose) and the repair
    draft fixes them, which is how the check-and-repair loop behaves with a real model."""

    def __init__(self, sloppy: bool = False):
        self.sloppy = sloppy

    def complete(self, system: str, prompt: str) -> str:
        f = json.loads(re.search(r"FACTS:\n(\{.*?\n\})", prompt, re.S).group(1))
        mistakes = self.sloppy and "YOUR DRAFT" not in prompt
        kpis = {k["metric"]: k for k in f["kpis"]}
        rev = kpis["Revenue"]
        reds = [k for k in f["kpis"] if k["status"] == "red"]
        greens = [k for k in f["kpis"] if k["favorable"] and k["vs_plan"] not in ("0", "+0")]
        gap = "$0.25M" if mistakes else rev["vs_plan"].lstrip("-")
        out = [f"Headline: {f['green']} of {f['kpi_count']} KPIs on plan, {f['red']} red. Revenue was "
               f"{rev['actual']}, {gap} below plan ({rev['vs_plan_pct']})."]
        for k in reds:
            verdict = "beat plan" if mistakes and k["direction"] == "lower is better" else "missed plan"
            out.append(f"{k['metric']} {verdict} at {k['actual']} vs {k['plan']} ({k['vs_plan']}); "
                       f"owner {k['owner']}.")
        if greens:
            out.append("Bright spots: " + ", ".join(f"{k['metric']} {k['actual']} vs {k['plan']}" for k in greens[:3])
                       + ".")
        b = f["revenue_bridge"]
        worst = next(iter(b["by_segment"].items()))
        out.append(f"Revenue bridge: volume {b['volume']}, mix {b['mix']}, price {b['price']}; "
                   f"{worst[0]} is the biggest drag at {worst[1]}.")
        out.append("Asks: " + "; ".join(f"{k['owner']} to bring a recovery plan for {k['metric']}" for k in reds[:3])
                   + ".")
        return "\n".join(out)


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "max_tokens": 700,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
