"""Chat-with-tools client interface: scripted mock, offline keyword planner, and a real Claude client.

Every client returns an assistant turn in Messages API shape:
    {"content": [{"type": "text", ...} | {"type": "tool_use", "id", "name", "input"}], "stop_reason": ...}
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class ChatLLM(Protocol):
    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> dict: ...


def text_turn(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


def tool_turn(name: str, args: dict, call_id: str = "t1", thought: str = "") -> dict:
    content = [{"type": "text", "text": thought}] if thought else []
    content.append({"type": "tool_use", "id": call_id, "name": name, "input": args})
    return {"content": content, "stop_reason": "tool_use"}


class ScriptedLLM:
    """Replays a fixed list of turns and records what it was shown. Used in tests."""

    def __init__(self, turns: list[dict]):
        self.turns = list(turns)
        self.seen: list[list[dict]] = []

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        self.seen.append([dict(m) for m in messages])
        if not self.turns:
            return text_turn("(script exhausted)")
        return self.turns.pop(0)


def _tool_results(messages: list[dict]) -> list[str]:
    out = []
    for m in messages:
        if m["role"] == "user" and isinstance(m["content"], list):
            out += [b["content"] for b in m["content"] if b.get("type") == "tool_result" and not b.get("is_error")]
    return out


class KeywordPlannerLLM:
    """Deterministic offline stand-in for the demo: look up a fact, then convert or compute.

    It is deliberately dumb; it shows the loop and tool plumbing without a network call.
    """

    UNIT_WORDS = {"btu": "BTU/h", "tons": "ton", "mw": "MW", "gallons": "gal"}

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        question = messages[0]["content"].lower()
        results = [json.loads(r) for r in _tool_results(messages)]
        keys = re.findall(r"[a-z0-9]+_?[a-z0-9]*\.[a-z_]+", question)
        step = len(results)
        if step < len(keys):
            return tool_turn("lookup", {"key": keys[step]}, f"call_{step}")
        values = [r["value"] for r in results[: len(keys)]]
        target = next((u for w, u in self.UNIT_WORDS.items() if w in question), None)
        if target and step == len(keys) and values:
            return tool_turn("convert_units", {"value": values[0], "from_unit": "kW", "to_unit": target}, f"call_{step}")
        if "/" in question and len(values) == 2 and step == len(keys):
            return tool_turn("calculator", {"expression": f"{values[0]} / {values[1]}"}, f"call_{step}")
        if "headroom" in question and len(values) == 2 and step == len(keys):
            return tool_turn("calculator", {"expression": f"{values[1]} - {values[0]}"}, f"call_{step}")
        if not results:
            return text_turn("I could not find a site metric in the question. Try a key like hall_a.it_load_kw.")
        final = results[-1]["value"] if isinstance(results[-1], dict) else results[-1]
        return text_turn(f"Answer: {final} (from {len(results)} tool call(s)).")


class AnthropicChatLLM:
    """Minimal Messages API client with tool use, standard library only."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        body = json.dumps({"model": self.model, "max_tokens": 1024, "system": system,
                           "messages": messages, "tools": tools}).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return {"content": data["content"], "stop_reason": data.get("stop_reason")}
