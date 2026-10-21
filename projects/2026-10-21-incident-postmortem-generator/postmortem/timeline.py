"""Parse logs and incident chat into one ordered, de-duplicated timeline with incident metrics."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

LOG_LINE = re.compile(r"^(\d\d:\d\d:\d\d) (\S+) (INFO|WARN|ERROR|CRIT) (.+)$")

# First matching rule wins. Order matters: "rolled back" is a mitigation even though it mentions a change.
RULES = [
    ("resolved", re.compile(r"\bresolved\b", re.I)),
    ("decision", re.compile(r"^decision:", re.I)),
    ("mitigation", re.compile(r"failover|rolled back|rollback|reset|mitigated|rejoined|redundancy restored", re.I)),
    ("change", re.compile(r"\bchange CHG-\d+ applied", re.I)),
    ("alert", re.compile(r"page sent", re.I)),
    ("ack", re.compile(r"^ack\b", re.I)),
    ("declare", re.compile(r"declaring SEV\d", re.I)),
    ("comms", re.compile(r"status page", re.I)),
    ("finding", re.compile(r"tripped|never replaced|wondering if related|can't reach|not pinging", re.I)),
]


def to_seconds(t: str) -> int:
    h, m, s = map(int, t.split(":"))
    return h * 3600 + m * 60 + s


def fmt_duration(sec: int) -> str:
    return f"{sec // 60}m{sec % 60:02d}s"


@dataclass
class Event:
    time: str
    source: str  # host/service for logs, person for chat
    text: str
    level: str = "CHAT"  # INFO/WARN/ERROR/CRIT for logs
    kind: str = "info"
    sources: list[str] = field(default_factory=list)

    @property
    def t(self) -> int:
        return to_seconds(self.time)

    @property
    def is_fault(self) -> bool:
        return self.level in ("ERROR", "CRIT")

    def render(self) -> str:
        who = self.source if len(self.sources) <= 1 else f"{self.sources[0]} (+{len(self.sources) - 1} more)"
        return f"{self.time}  [{self.kind:<10}] {who}: {self.text}"


def classify(text: str, level: str) -> str:
    for kind, rx in RULES:
        if rx.search(text):
            return kind
    if level in ("ERROR", "CRIT"):
        return "fault"
    if level == "WARN":
        return "symptom"
    return "info"


def parse_logs(text: str) -> list[Event]:
    events = []
    for line in text.splitlines():
        m = LOG_LINE.match(line.strip())
        if m:
            t, src, level, msg = m.groups()
            events.append(Event(t, src, msg, level, classify(msg, level), [src]))
    return events


def parse_chat(text: str) -> list[Event]:
    events = []
    for line in text.splitlines():
        if line.strip():
            r = json.loads(line)
            events.append(Event(r["time"], r["user"], r["text"], "CHAT", classify(r["text"], "CHAT"), [r["user"]]))
    return events


def collapse(events: list[Event], window: int = 60) -> list[Event]:
    """Merge repeats of the same log message within a window (one host or many) into a single event."""
    out: list[Event] = []
    for e in events:
        match = None
        if e.level != "CHAT":
            match = next((p for p in reversed(out) if e.t - p.t <= window and p.level == e.level and p.text == e.text), None)
        if match is None:
            out.append(e)
        elif e.source not in match.sources:
            match.sources.append(e.source)
    return out


def build_timeline(log_text: str, chat_text: str) -> list[Event]:
    merged = sorted(parse_logs(log_text) + parse_chat(chat_text), key=lambda e: (e.t, e.level == "CHAT"))
    return collapse(merged)


@dataclass(frozen=True)
class Metrics:
    start: str
    detected: str | None
    acknowledged: str | None
    mitigated: str | None
    resolved: str | None
    suspected_change: str | None

    def durations(self) -> dict[str, str]:
        out = {}
        for name, t in (("time_to_detect", self.detected), ("time_to_acknowledge", self.acknowledged),
                        ("time_to_mitigate", self.mitigated), ("time_to_resolve", self.resolved)):
            if t:
                out[name] = fmt_duration(to_seconds(t) - to_seconds(self.start))
        return out


def first(events: list[Event], kind: str, after: int = 0) -> Event | None:
    return next((e for e in events if e.kind == kind and e.t >= after), None)


def compute_metrics(events: list[Event], change_lookback: int = 3600) -> Metrics:
    fault = next((e for e in events if e.is_fault), None)
    if fault is None:
        raise ValueError("no ERROR/CRIT events: nothing to write a postmortem about")
    # Customer impact is mitigated when a person says so; facility repairs before that don't count.
    mitigated = next((e for e in events if e.level == "CHAT" and "mitigated" in e.text.lower()), None)
    change = next((e for e in reversed(events) if e.kind == "change" and 0 <= fault.t - e.t <= change_lookback), None)
    get = lambda k: (first(events, k, fault.t) or Event("", "", "")).time or None  # noqa: E731
    return Metrics(fault.time, get("alert"), get("ack"), mitigated.time if mitigated else None, get("resolved"),
                   change.text if change else None)


def load_timeline(data_dir: Path) -> list[Event]:
    return build_timeline((data_dir / "syslog.log").read_text(), (data_dir / "chat.jsonl").read_text())
