"""Placement heuristics: first-fit / best-fit / worst-fit decreasing, plus a consolidation pass.

Hard constraints checked for every placement:
  * U-space and per-feed power budget of the rack
  * anti-affinity: two members of the same group never share a rack
  * row spread: at most ceil(group_size / n_rows) members of a group per row,
    so losing a row (PDU, cooling zone) never takes out a whole service
"""
from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import dataclass, field

from .model import Rack, Server

STRATEGIES = ("first_fit", "best_fit", "worst_fit")


@dataclass
class Plan:
    strategy: str
    racks: list[Rack]
    unplaced: list[tuple[Server, str]] = field(default_factory=list)

    def rack_of(self, server_id: str) -> Rack | None:
        return next((r for r in self.racks if any(s.id == server_id for s in r.servers)), None)


def dominant_size(s: Server, u_ref: int, kw_ref: float) -> float:
    """Size of a server as its largest share of a reference rack (dominant resource)."""
    return max(s.u / u_ref, s.kw / kw_ref)


class Placer:
    def __init__(self, racks: list[Rack], servers: list[Server]):
        self.base_racks = racks
        self.servers = servers
        self.rows = sorted({r.row for r in racks})
        self.group_sizes = Counter(s.group for s in servers if s.group)
        self.u_ref = max(r.u_capacity for r in racks)
        self.kw_ref = max(r.kw_capacity for r in racks)

    def max_per_row(self, group: str) -> int:
        return math.ceil(self.group_sizes[group] / len(self.rows))

    def violation(self, rack: Rack, s: Server, racks: list[Rack]) -> str | None:
        if s.u > rack.free_u:
            return "u_space"
        if s.kw > rack.free_kw + 1e-9:
            return "power"
        if s.group:
            if any(o.group == s.group for o in rack.servers):
                return "anti_affinity"
            in_row = sum(1 for r in racks if r.row == rack.row for o in r.servers if o.group == s.group)
            if in_row >= self.max_per_row(s.group):
                return "row_spread"
        return None

    def _order(self) -> list[Server]:
        # Big items first; grouped items before loose ones of equal size because they have fewer legal homes.
        return sorted(self.servers, key=lambda s: (-dominant_size(s, self.u_ref, self.kw_ref), s.group == "", s.id))

    def _slack_after(self, rack: Rack, s: Server) -> float:
        return min((rack.free_u - s.u) / rack.u_capacity, (rack.free_kw - s.kw) / rack.kw_capacity)

    def _choose(self, strategy: str, legal: list[Rack], s: Server) -> Rack:
        # Prefer racks that are already powered on: opening an empty rack is the real cost.
        opened = [r for r in legal if r.in_use] or legal
        if strategy == "first_fit":
            return opened[0]
        if strategy == "best_fit":
            return min(opened, key=lambda r: (self._slack_after(r, s), r.id))
        if strategy == "worst_fit":
            return max(legal, key=lambda r: (self._slack_after(r, s), r.id))
        raise ValueError(f"unknown strategy {strategy}")

    def place(self, strategy: str = "best_fit", consolidate: bool = True) -> Plan:
        racks = copy.deepcopy(self.base_racks)
        plan = Plan(strategy, racks)
        for s in self._order():
            reasons = {r.id: self.violation(r, s, racks) for r in racks}
            legal = [r for r in racks if reasons[r.id] is None]
            if not legal:
                plan.unplaced.append((s, Counter(reasons.values()).most_common(1)[0][0]))
                continue
            self._choose(strategy, legal, s).servers.append(s)
        if consolidate and strategy != "worst_fit":
            self.consolidate(plan)
        return plan

    def consolidate(self, plan: Plan) -> int:
        """Try to empty the lightest greenfield racks by moving their servers into other used racks."""
        drained = 0
        while True:
            candidates = sorted(
                (r for r in plan.racks if r.servers and r.used_u == 0),
                key=lambda r: (sum(s.kw for s in r.servers), r.id),
            )
            for victim in candidates:
                if self._try_drain(plan, victim):
                    drained += 1
                    break
            else:
                return drained

    def _try_drain(self, plan: Plan, victim: Rack) -> bool:
        snapshot = [list(r.servers) for r in plan.racks]  # restore in place so callers' rack refs stay valid
        moving, victim.servers = victim.servers, []
        for s in sorted(moving, key=lambda x: -dominant_size(x, self.u_ref, self.kw_ref)):
            targets = [r for r in plan.racks if r is not victim and r.in_use and self.violation(r, s, plan.racks) is None]
            if not targets:
                for r, saved in zip(plan.racks, snapshot):
                    r.servers = saved
                return False
            min(targets, key=lambda r: (self._slack_after(r, s), r.id)).servers.append(s)
        return True


@dataclass(frozen=True)
class Metrics:
    racks_used: int
    new_racks_opened: int
    unplaced: int
    stranded_kw: float  # power left in used racks that no server in the catalog can use
    stranded_u: int
    max_rack_util: float
    lower_bound_racks: int


def evaluate(plan: Plan, catalog: list[Server]) -> Metrics:
    used = [r for r in plan.racks if r.in_use]
    min_u = min(s.u for s in catalog)
    min_kw = min(s.kw for s in catalog)
    stranded_kw = stranded_u = 0.0
    for r in used:
        if r.free_u < min_u:
            stranded_kw += r.free_kw  # power with no space to use it
        elif r.free_kw < min_kw:
            stranded_u += r.free_u  # space with no power to use it
    total_u = sum(r.used_u for r in plan.racks) + sum(s.u for s in catalog)
    total_kw = sum(r.used_kw for r in plan.racks) + sum(s.kw for s in catalog)
    cap_u = max(r.u_capacity for r in plan.racks)
    cap_kw = max(r.kw_capacity for r in plan.racks)
    groups = Counter(s.group for s in catalog if s.group)
    util = max(1 - r.free_kw / r.kw_capacity for r in used) if used else 0.0
    return Metrics(
        racks_used=len(used),
        new_racks_opened=sum(1 for r in used if r.used_u == 0),
        unplaced=len(plan.unplaced),
        stranded_kw=round(stranded_kw, 2),
        stranded_u=int(stranded_u),
        max_rack_util=round(util, 3),
        # A group of n replicas needs n distinct racks, which can dominate the space/power bound.
        lower_bound_racks=max(math.ceil(total_u / cap_u), math.ceil(total_kw / cap_kw), max(groups.values(), default=0)),
    )


def validate(plan: Plan, placer: Placer) -> list[str]:
    """Independent re-check of every hard constraint; returns human-readable violations."""
    problems = []
    for r in plan.racks:
        if r.free_u < 0:
            problems.append(f"{r.id}: over U capacity by {-r.free_u}U")
        if r.free_kw < -1e-9:
            problems.append(f"{r.id}: over power budget by {-r.free_kw:.2f} kW")
        dup = [g for g, n in Counter(s.group for s in r.servers if s.group).items() if n > 1]
        problems += [f"{r.id}: group {g} has replicas sharing the rack" for g in dup]
    for g in placer.group_sizes:
        per_row = Counter(r.row for r in plan.racks for s in r.servers if s.group == g)
        if per_row and max(per_row.values()) > placer.max_per_row(g):
            problems.append(f"group {g}: too many replicas in one row {dict(per_row)}")
    return problems
