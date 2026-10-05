"""Shared blackboard: every agent reads the whole log and appends typed entries."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Entry:
    round: int
    author: str  # planner | executor | critic | orchestrator
    kind: str  # plan | result | error | critique | approval | draft | note
    content: str


@dataclass
class Scratchpad:
    entries: list[Entry] = field(default_factory=list)
    variables: dict[str, float] = field(default_factory=dict)

    def add(self, round_: int, author: str, kind: str, content: str) -> Entry:
        e = Entry(round_, author, kind, content)
        self.entries.append(e)
        return e

    def latest(self, kind: str) -> Entry | None:
        return next((e for e in reversed(self.entries) if e.kind == kind), None)

    def render(self, kinds: set[str] | None = None) -> str:
        return "\n".join(f"[r{e.round} {e.author}:{e.kind}] {e.content}"
                         for e in self.entries if kinds is None or e.kind in kinds)
