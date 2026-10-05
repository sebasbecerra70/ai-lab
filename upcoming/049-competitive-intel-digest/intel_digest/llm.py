"""LLM client interface: a deterministic mock for tests, and a real Claude client via stdlib HTTP."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from collections import defaultdict
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class MockLLM:
    """Summarizes high and medium changes per competitor, citing change ids, with a templated 'so what'."""

    def complete(self, system: str, prompt: str) -> str:
        ours = set(re.search(r"^OUR DIFFERENTIATORS: (.+)$", prompt, re.M).group(1).split(", "))
        rows = re.findall(r"^\[(C\d+)\] (\w+) \| (high|medium|low) \| (\w+) \| (.+)$", prompt, re.M)
        by_comp: dict[str, list] = defaultdict(list)
        for cid, comp, sev, kind, detail in rows:
            if sev != "low":
                by_comp[comp].append((cid, sev, kind, detail))
        out = []
        for comp, items in by_comp.items():
            out.append(f"## {comp}")
            for cid, sev, kind, detail in items:
                out.append(f"- {detail} [{cid}]")
            so_what = []
            overlap = sorted({d for d in ours for _, _, _, det in items if d in det})
            if overlap:
                cites = " ".join(f"[{c}]" for c, _, _, det in items if any(d in det for d in overlap))
                so_what.append(f"now matches our differentiators ({', '.join(overlap)}) {cites}")
            prices = dict(re.findall(r"(\w+) \$(\d+)", re.search(r"^OUR PRICES: (.+)$", prompt, re.M).group(1)))
            for c, _, k, det in items:
                m = re.match(r"(\w+): \$[\d,]+/\w+ -> \$([\d,]+)/", det)
                if k == "price_increase" and m and m.group(1) in prices:
                    gap = int(m.group(2).replace(",", "")) - int(prices[m.group(1)])
                    where = f"${abs(gap)} {'above' if gap > 0 else 'below'}"
                    so_what.append(f"{m.group(1)} is now {where} our {m.group(1)} price [{c}]")
            new_plans = [c for c, _, k, _ in items if k == "plan_added"]
            if new_plans:
                so_what.append(f"added a plan to capture a new segment {' '.join(f'[{c}]' for c in new_plans)}")
            if so_what:
                out.append(f"So what: {comp} " + "; ".join(so_what) + ".")
            out.append("")
        return "\n".join(out).strip() or "No material competitor changes this period."


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "max_tokens": 1200,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
