"""On-call summary: structured incident facts in, a short human summary out (LLM or template)."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol

from .triage import Incident, fmt_time

SYSTEM = (
    "You are an SRE writing a handover for the on-call engineer. Use ONLY the incident facts given. "
    "For each incident, in severity order, give one line: severity, what is happening, likely root cause, "
    "first action. Then one line listing what can wait until morning. No speculation beyond the facts."
)


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


FIRST_ACTION = {
    "power": "dispatch DC tech to the PDU, confirm feed A status with facilities, shed load if feed B > 80%",
    "cooling": "page facilities for the CRAC, check rack inlet temps, open contingency cooling",
    "network": "check the uplink optic/cable on the ToR, fail traffic to the redundant uplink",
}


def incident_facts(incidents: list[Incident]) -> list[dict]:
    facts = []
    for i, inc in enumerate(incidents, 1):
        facts.append({
            "id": i,
            "severity": inc.severity,
            "started": fmt_time(inc.first),
            "root_cause_candidate": inc.root_cause,
            "alerts": inc.alert_count,
            "services": inc.services,
            "signals": [f"{g.host}:{g.check} x{len(g.alerts)} ({g.alerts[-1].message})" for g in inc.groups],
        })
    return facts


class TemplateLLM:
    """Deterministic summary writer used offline. It reads the same JSON facts the real model gets."""

    def complete(self, system: str, prompt: str) -> str:
        facts = json.loads(prompt.split("FACTS:\n", 1)[1])
        lines, later = [], []
        for f in facts:
            if f["severity"] == "SEV4":
                later.append(f"{f['root_cause_candidate']} ({f['signals'][0].split(' (')[0]})")
                continue
            sig = " ".join(f["signals"])
            kind = next((k for k, words in (("power", "pdu"), ("cooling", "supply_temp"), ("network", "flap"))
                         if words in sig), None)
            action = FIRST_ACTION.get(kind, "check the host and recent changes")
            impact = ", ".join(f["services"]) or "no customer-facing services yet"
            lines.append(f"- {f['severity']} since {f['started']}: {f['alerts']} alerts, likely cause "
                         f"{f['root_cause_candidate']}; impact: {impact}. First action: {action}.")
        if later:
            lines.append(f"- Can wait until morning: {'; '.join(later)}.")
        return "\n".join(lines)


class AnthropicLLM:
    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": 800, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")


def draft_summary(incidents: list[Incident], llm: LLMClient) -> str:
    prompt = "FACTS:\n" + json.dumps(incident_facts(incidents), indent=1)
    return llm.complete(SYSTEM, prompt)
