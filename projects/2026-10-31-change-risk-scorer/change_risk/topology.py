"""Dependency graph with redundancy groups, and a failure simulator.

Each node lists dependency *groups*. A node stays up while every group still has one live member, so
["pdu-A1", "pdu-B1"] is a dual-corded feed (either PDU keeps the rack up) and [["pdu-A2"]] is single-corded.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    depends_on: tuple[tuple[str, ...], ...]
    customer_facing: bool = False


@dataclass
class Outage:
    down: set[str]  # everything that loses power/connectivity/service, targets included
    degraded: set[str]  # still up, but running without its redundant path

    def customer_down(self, topo: dict[str, Node]) -> list[str]:
        return sorted(n for n in self.down if topo[n].customer_facing)


def load_topology(path: Path) -> dict[str, Node]:
    raw = json.loads(path.read_text())["nodes"]
    topo = {k: Node(k, v["kind"], tuple(tuple(g) for g in v["depends_on"]), v.get("customer_facing", False))
            for k, v in raw.items()}
    for n in topo.values():
        for group in n.depends_on:
            for dep in group:
                if dep not in topo:
                    raise ValueError(f"{n.id} depends on unknown node {dep}")
    return topo


def simulate(topo: dict[str, Node], failed: set[str]) -> Outage:
    """Propagate failures to a fixed point: a node goes down when any of its groups is entirely down."""
    unknown = failed - topo.keys()
    if unknown:
        raise ValueError(f"unknown targets: {sorted(unknown)}")
    down = set(failed)
    changed = True
    while changed:
        changed = False
        for n in topo.values():
            if n.id not in down and any(all(m in down for m in g) for g in n.depends_on):
                down.add(n.id)
                changed = True
    degraded = {n.id for n in topo.values() if n.id not in down
                and any(len(g) > 1 and any(m in down for m in g) for g in n.depends_on)}
    return Outage(down, degraded)


def single_points_of_failure(topo: dict[str, Node], failed: set[str]) -> dict[str, list[str]]:
    """While `failed` is out, which one extra failure would take a customer-facing service down?

    This is the N+0 exposure a CAB should see: a UPS swap looks harmless until you notice the other
    UPS is now carrying every customer on its own.
    """
    base = set(simulate(topo, failed).customer_down(topo))
    spofs = {}
    for n in topo:
        if n in failed:
            continue
        lost = set(simulate(topo, failed | {n}).customer_down(topo)) - base
        if lost and n not in lost:
            spofs[n] = sorted(lost)
    # keep only spofs that are new because of the change
    always = {n for n in spofs if set(simulate(topo, {n}).customer_down(topo)) - {n}}
    return {n: v for n, v in spofs.items() if n not in always}
