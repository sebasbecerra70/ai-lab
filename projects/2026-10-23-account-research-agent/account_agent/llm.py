"""LLM client interface: a deterministic research policy for tests/offline, and a real Claude client."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol

# Which product capability addresses which pain, used by the offline policy to write the brief.
PLAYS = {
    "stockout": "replenishment",
    "overstock": "forecasting",
    "markdown": "forecasting",
    "spreadsheet": "replenishment",
    "transfers": "rebalancing",
    "s/4hana": "integrations",
    "manhattan": "integrations",
}
PAIN_QUERY = "stockouts lost sales overstock markdowns spreadsheets manual transfers"


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


def _section(prompt: str, name: str) -> str:
    m = re.search(rf"^{name}:\n(.*?)(?=^\w+:\n|\Z)", prompt, re.S | re.M)
    return m.group(1).strip() if m else ""


class MockLLM:
    """Scripted researcher: a fixed plan that adapts to what it finds (missing account, missing section)."""

    def complete(self, system: str, prompt: str) -> str:
        target = _section(prompt, "TARGET")
        history = json.loads(_section(prompt, "HISTORY") or "[]")
        called = [(h["tool"], json.dumps(h["args"], sort_keys=True)) for h in history]

        def act(tool: str, **args) -> str | None:
            if (tool, json.dumps(args, sort_keys=True)) in called:
                return None
            return json.dumps({"thought": f"next: {tool}", "tool": tool, "args": args})

        if not history:
            return act("list_companies")
        companies = history[0]["observation"]
        doc = next((c["doc"] for c in companies if c["name"].lower() == target.lower()), None)
        if doc is None:
            return json.dumps({"final": f"# Account brief: {target}\n\nNo profile found for {target}; research manually."})
        plan = [
            ("read_section", {"doc": doc, "section": "Overview"}),
            ("score_fit", {"doc": doc}),
            ("read_section", {"doc": doc, "section": "Recent news"}),
            ("read_section", {"doc": doc, "section": "Leadership"}),
            ("search", {"query": PAIN_QUERY, "doc": doc}),
            ("read_section", {"doc": "our_product", "section": "Capabilities"}),
        ]
        for tool, args in plan:
            nxt = act(tool, **args)
            if nxt:
                return nxt
        return json.dumps({"final": self._brief(target, doc, history)})

    def _brief(self, target: str, doc: str, history: list[dict]) -> str:
        obs = {(h["tool"], h["args"].get("section", "")): h["observation"] for h in history}
        overview = obs[("read_section", "Overview")]
        fit = obs[("score_fit", "")]
        news = obs[("read_section", "Recent news")]
        leaders = obs[("read_section", "Leadership")]
        hits = obs[("search", "")]
        caps = obs[("read_section", "Capabilities")]
        cap_lines = {ln.split(":")[0].strip("- ").strip(): ln for ln in caps.get("text", "").splitlines() if ":" in ln}

        lines = [f"# Account brief: {target}", "", "## Snapshot", f"- {overview['text'].split('. ')[0]}. [{overview['ref']}]", "",
                 f"## Fit: {fit['score']}/{fit['max']}"]
        for r in fit["reasons"]:
            mark = "met" if r["met"] else "not met"
            lines.append(f"- {r['criterion']}: {mark}" + (f" ({r['evidence']}) [{r['ref']}]" if r["ref"] else " (no evidence)"))
        lines += ["", "## Why now"]
        lines += [f"- {ln.lstrip('- ').strip()} [{news['ref']}]" for ln in news.get("text", "").splitlines() if ln.strip()]
        lines += ["", "## Pains and plays"]
        seen = set()
        for h in hits:
            low = h["snippet"].lower()
            for pain, cap in PLAYS.items():
                if pain in low and cap not in seen and cap in cap_lines:
                    seen.add(cap)
                    lines.append(f"- {pain} -> {cap} [{h['ref']}] [{caps['ref']}]")
        lines += ["", "## Who to talk to"]
        keep = re.compile(r"supply chain|planning|financial|operations|distribution", re.I)
        lines += [f"- {ln.lstrip('- ').strip()} [{leaders['ref']}]" for ln in leaders.get("text", "").splitlines() if keep.search(ln)]
        first_news = next((ln.lstrip("- ").strip() for ln in news.get("text", "").splitlines() if ln.strip()), "")
        headline = first_news.split(", ")[0].rstrip(".")
        lines += ["", "## Suggested opener",
                  f"Saw that {target} {headline[:1].lower()}{headline[1:]}. Teams opening a DC usually re-set replenishment rules "
                  f"at the same time; worth 20 minutes to compare notes on how others cut stockouts during the transition?"]
        return "\n".join(lines)


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": 1500, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
