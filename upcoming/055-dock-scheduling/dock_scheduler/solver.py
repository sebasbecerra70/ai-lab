"""Three ways to build a door plan: the dispatcher's rotation, a greedy rule, and local search on top of greedy."""
from __future__ import annotations

import random

from .model import CHANGEOVER_MIN, Door, Plan, Truck, compatible, door_cost, service_min


def rotation(trucks: list[Truck], doors: list[Door]) -> Plan:
    """Baseline: the clerk sends each arriving truck to the next compatible door in turn, ignoring queues."""
    plan: Plan = {d.name: [] for d in doors}
    i = 0
    for t in sorted(trucks, key=lambda t: t.arrival):
        for k in range(len(doors)):
            d = doors[(i + k) % len(doors)]
            if compatible(t, d):
                plan[d.name].append(t)
                i = (i + k + 1) % len(doors)
                break
        else:
            raise ValueError(f"no compatible door for {t.name}")
    return plan


def greedy(trucks: list[Truck], doors: list[Door]) -> Plan:
    """Earliest finish: in arrival order, put each truck on the door where it would finish first.
    Ties go to dry doors so reefer doors stay free for the trucks that can only use them."""
    plan: Plan = {d.name: [] for d in doors}
    free = {d.name: float(d.opens) for d in doors}
    for t in sorted(trucks, key=lambda t: (t.arrival, -t.reefer)):
        best = None
        for d in doors:
            if not compatible(t, d):
                continue
            start = max(float(t.arrival), free[d.name] + (CHANGEOVER_MIN if plan[d.name] else 0))
            key = (start + service_min(t, d), d.reefer and not t.reefer)
            if best is None or key < best[0]:
                best = (key, d)
        if best is None:
            raise ValueError(f"no compatible door for {t.name}")
        d = best[1]
        plan[d.name].append(t)
        free[d.name] = best[0][0]
    return plan


def _moves(plan: Plan, doors: dict[str, Door]):
    """Relocate one truck to any position on any compatible door, or swap two trucks across doors.
    Yields only the changed door sequences: {door: new_seq}."""
    names = list(plan)
    for a in names:
        for i, t in enumerate(plan[a]):
            src = plan[a][:i] + plan[a][i + 1:]
            for b in names:
                if not compatible(t, doors[b]):
                    continue
                if a == b:
                    for j in range(len(src) + 1):
                        if j != i:
                            yield {a: src[:j] + [t] + src[j:]}
                else:
                    for j in range(len(plan[b]) + 1):
                        yield {a: src, b: plan[b][:j] + [t] + plan[b][j:]}
    for x, a in enumerate(names):
        for b in names[x + 1:]:
            for i, t in enumerate(plan[a]):
                for j, u in enumerate(plan[b]):
                    if compatible(t, doors[b]) and compatible(u, doors[a]):
                        yield {a: plan[a][:i] + [u] + plan[a][i + 1:], b: plan[b][:j] + [t] + plan[b][j + 1:]}


def descend(plan: Plan, doors: dict[str, Door], max_rounds: int = 500) -> tuple[Plan, list[float]]:
    """Best-improvement descent. Cost is a sum over doors, so each move is priced by re-costing two doors."""
    current = dict(plan)
    per_door = {n: door_cost(seq, doors[n]) for n, seq in current.items()}
    history = [sum(per_door.values())]
    for _ in range(max_rounds):
        best, best_delta = None, -1e-9
        for change in _moves(current, doors):
            delta = sum(door_cost(seq, doors[n]) - per_door[n] for n, seq in change.items())
            if delta < best_delta:
                best, best_delta = change, delta
        if best is None:
            break
        for n, seq in best.items():
            current[n] = seq
            per_door[n] = door_cost(seq, doors[n])
        history.append(sum(per_door.values()))
    return current, history


def _kick(plan: Plan, doors: dict[str, Door], rng: random.Random, k: int) -> Plan:
    """Perturbation: move k random trucks to random compatible doors and positions."""
    new = {n: list(seq) for n, seq in plan.items()}
    for _ in range(k):
        a = rng.choice([n for n in new if new[n]])
        t = new[a].pop(rng.randrange(len(new[a])))
        b = rng.choice([n for n in new if compatible(t, doors[n])])
        new[b].insert(rng.randrange(len(new[b]) + 1), t)
    return new


def local_search(plan: Plan, doors: list[Door], kicks: int = 30, k: int = 3, seed: int = 0) -> tuple[Plan, list[float]]:
    """Iterated local search: descend, then repeatedly kick the best plan and descend again, keeping
    improvements. Plain descent stalls in local minima where every single move or swap looks worse.
    Returns the best plan and the best cost after each accepted improvement."""
    by_name = {d.name: d for d in doors}
    rng = random.Random(seed)
    best, hist = descend(plan, by_name)
    history = [hist[0], hist[-1]] if len(hist) > 1 else hist
    best_cost = hist[-1]
    for _ in range(kicks):
        cand, h = descend(_kick(best, by_name, rng, k), by_name)
        if h[-1] < best_cost - 1e-9:
            best, best_cost = cand, h[-1]
            history.append(best_cost)
    return best, history
