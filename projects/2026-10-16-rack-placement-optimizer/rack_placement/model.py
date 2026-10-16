"""Domain objects and CSV loading for racks and servers."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Server:
    id: str
    model: str
    u: int
    kw: float
    group: str = ""  # anti-affinity group: replicas of one service; "" means no constraint


@dataclass
class Rack:
    id: str
    row: str
    u_capacity: int  # usable U after ToR switch and patch panels
    kw_capacity: float  # per-feed budget at 80% breaker derate, so a 2N rack survives losing one feed
    used_u: int = 0  # brownfield load already in the rack
    used_kw: float = 0.0
    servers: list[Server] = field(default_factory=list)

    @property
    def free_u(self) -> int:
        return self.u_capacity - self.used_u - sum(s.u for s in self.servers)

    @property
    def free_kw(self) -> float:
        return round(self.kw_capacity - self.used_kw - sum(s.kw for s in self.servers), 3)

    @property
    def in_use(self) -> bool:
        return self.used_u > 0 or bool(self.servers)

    def fits(self, s: Server) -> bool:
        return s.u <= self.free_u and s.kw <= self.free_kw + 1e-9


def load_servers(path: Path) -> list[Server]:
    with open(path, newline="") as f:
        return [Server(r["id"], r["model"], int(r["u"]), float(r["kw"]), r["group"]) for r in csv.DictReader(f)]


def load_racks(path: Path) -> list[Rack]:
    with open(path, newline="") as f:
        return [
            Rack(r["id"], r["row"], int(r["u_capacity"]), float(r["kw_capacity"]), int(r["used_u"]), float(r["used_kw"]))
            for r in csv.DictReader(f)
        ]
