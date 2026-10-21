"""Turn a timeline into grounded facts, ask the LLM for a blameless draft, and lint the result."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .llm import LLMClient
from .timeline import Event, Metrics, fmt_duration, to_seconds

SYSTEM = (
    "You write blameless incident postmortems for a data center operations team. Use ONLY the FACTS provided; "
    "never invent times, systems or causes. Describe what systems and processes allowed the failure, not who erred: "
    "no names next to mistakes, no 'should have', no 'human error'. Sections: Summary, Impact, Timeline, Root cause and "
    "contributing factors, What went well, What was hard, Action items (priority, owner role). Markdown only."
)

KEY_KINDS = {"change", "fault", "alert", "ack", "declare", "comms", "finding", "mitigation", "decision", "resolved"}

BLAME_PATTERNS = [
    r"\bhuman error\b", r"\bshould have\b", r"\bcareless(ly)?\b", r"\bfault of\b", r"'s fault\b", r"\bfailed to\b",
    r"\bnegligen(t|ce)\b", r"\bblame[ds]?\b", r"\bmistake by\b",
]


def action_items(events: list[Event], m: Metrics) -> list[dict]:
    """Rule-based candidate actions. The LLM may reword them but gets them as facts, so nothing is invented."""
    items = []
    if m.suspected_change:
        items.append({"priority": "P1", "owner": "facilities engineering",
                      "action": "Canary PDU firmware on one non-critical PDU with a 24h soak before fleet rollout"})
    if any("never replaced" in e.text or "PSU1 absent" in e.text for e in events):
        items.append({"priority": "P1", "owner": "DC operations",
                      "action": "Daily check for hosts running on a single PSU; block RMA tickets from closing until the part is reinstalled"})
    if m.detected and to_seconds(m.detected) - to_seconds(m.start) > 60:
        items.append({"priority": "P2", "owner": "SRE",
                      "action": "Page directly on PDU breaker-trip events instead of waiting for customer-facing error rates"})
    if any(e.kind == "mitigation" and "failover" in e.text and e.level == "CHAT" for e in events):
        items.append({"priority": "P2", "owner": "database team",
                      "action": "Make db failover automatic when the primary's host loses power"})
    return items


def went_well_and_poorly(events: list[Event], m: Metrics) -> tuple[list[str], list[str]]:
    """Derive the retrospective bullets from the timeline so the LLM never has to guess them."""
    well, poorly = [], []
    start = to_seconds(m.start)
    alert = next((e for e in events if e.kind == "alert"), None)
    declare = next((e for e in events if e.kind == "declare"), None)
    comms = next((e for e in events if e.kind == "comms"), None)
    finding = next((e for e in events if e.kind == "finding" and "breaker" in e.text), None)
    first_fault = next(e for e in events if e.is_fault)
    if alert and first_fault.source not in alert.text:
        poorly.append(f"The first page ({alert.text.split(': ')[-1]}) came from a customer-facing symptom "
                      f"{fmt_duration(alert.t - start)} after the first fault on {first_fault.source}, which paged no one.")
    if any(e.kind == "mitigation" and "manual" in e.text for e in events):
        poorly.append("Database failover needed a human to trigger it.")
    if m.mitigated:
        well.append(f"Customer impact was mitigated {fmt_duration(to_seconds(m.mitigated) - start)} after the first fault.")
    if declare and comms and comms.t - declare.t <= 300:
        well.append(f"Status page was updated {fmt_duration(comms.t - declare.t)} after the incident was declared.")
    if finding:
        well.append(f"Facilities found the physical fault {fmt_duration(finding.t - start)} in, while software mitigation ran in parallel.")
    return well, poorly


def build_facts(events: list[Event], m: Metrics, title: str, roles: dict[str, str] | None = None) -> dict:
    roles = roles or {}
    first_fault = next(e for e in events if e.is_fault)
    impact_events = [e for e in events if "5xx rate" in e.text]
    peak = max((float(re.search(r"([\d.]+)%", e.text).group(1)) for e in impact_events), default=None)
    well, poorly = went_well_and_poorly(events, m)

    def blameless(e: Event) -> str:
        # Roles, not names: a postmortem is about the system, not the person on call.
        line = e.render()
        for name, role in roles.items():
            line = re.sub(rf"\b{re.escape(name)}\b", role, line)
        return line

    return {
        "title": title,
        "start": m.start,
        "first_fault": f"{first_fault.source}: {first_fault.text}",
        "detected": m.detected, "acknowledged": m.acknowledged, "mitigated": m.mitigated, "resolved": m.resolved,
        "durations": m.durations(),
        "impact": f"checkout 5xx rate peaked at {peak}% (threshold 2%)" if peak is not None else "see timeline",
        "suspected_change": m.suspected_change,
        "key_events": [blameless(e) for e in events if e.kind in KEY_KINDS],
        "findings": [blameless(e).split(": ", 1)[1] for e in events if e.kind == "finding" and e.level == "CHAT"],
        "went_well": well,
        "went_poorly": poorly,
        "action_items": action_items(events, m),
    }


def draft_postmortem(llm: LLMClient, facts: dict) -> str:
    return llm.complete(SYSTEM, "Write the postmortem.\nFACTS:\n" + json.dumps(facts, indent=1))


@dataclass(frozen=True)
class LintResult:
    blame_phrases: list[str]
    unknown_times: list[str]  # times in the draft that are not in the facts
    missing_sections: list[str]

    @property
    def ok(self) -> bool:
        return not (self.blame_phrases or self.unknown_times or self.missing_sections)


REQUIRED_SECTIONS = ["Summary", "Impact", "Timeline", "Root cause", "Action items"]


def lint(draft: str, facts: dict) -> LintResult:
    blame = [m.group(0) for p in BLAME_PATTERNS for m in re.finditer(p, draft, re.I)]
    known = set(re.findall(r"\b\d\d:\d\d(?::\d\d)?\b", json.dumps(facts)))
    known |= {t[:5] for t in known}  # allow "02:14" for "02:14:05"
    times = re.findall(r"\b\d\d:\d\d(?::\d\d)?\b", draft)
    unknown = sorted({t for t in times if t not in known})
    missing = [s for s in REQUIRED_SECTIONS if not re.search(rf"^#+\s*{s}", draft, re.M | re.I)]
    return LintResult(blame, unknown, missing)
