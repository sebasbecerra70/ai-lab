"""Capacitated vehicle routing: nearest-neighbour baseline, Clarke-Wright savings, and 2-opt improvement."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

ROAD_FACTOR = 1.3  # straight-line km to road km, typical for a metro grid


@dataclass(frozen=True)
class Stop:
    id: str
    name: str
    x: float
    y: float
    demand: int


@dataclass(frozen=True)
class Problem:
    depot: Stop
    stops: tuple[Stop, ...]
    capacity: int  # pallets per truck
    max_route_km: float = math.inf  # driver shift limit expressed as distance

    def __post_init__(self):
        too_big = [s.id for s in self.stops if s.demand > self.capacity]
        if too_big:
            raise ValueError(f"stops exceed truck capacity: {too_big}")


def load_problem(path: Path, capacity: int, max_route_km: float = math.inf) -> Problem:
    with open(path, newline="") as f:
        rows = [Stop(r["id"], r["name"], float(r["x_km"]), float(r["y_km"]), int(r["pallets"])) for r in csv.DictReader(f)]
    return Problem(rows[0], tuple(rows[1:]), capacity, max_route_km)


def dist(a: Stop, b: Stop) -> float:
    return math.hypot(a.x - b.x, a.y - b.y) * ROAD_FACTOR


def route_km(depot: Stop, route: list[Stop]) -> float:
    path = [depot, *route, depot]
    return sum(dist(a, b) for a, b in zip(path, path[1:]))


def load(route: list[Stop]) -> int:
    return sum(s.demand for s in route)


def nearest_neighbour(p: Problem) -> list[list[Stop]]:
    """Baseline a dispatcher might do by hand: keep driving to the closest stop that still fits."""
    left = list(p.stops)
    routes = []
    while left:
        route, here = [], p.depot
        while True:
            fits = [s for s in left if load(route) + s.demand <= p.capacity and route_km(p.depot, route + [s]) <= p.max_route_km]
            if not fits:
                break
            here = min(fits, key=lambda s: (dist(here, s), s.id))
            route.append(here)
            left.remove(here)
        if not route:
            raise ValueError(f"stop {left[0].id} cannot be served within the route limit")
        routes.append(route)
    return routes


def clarke_wright(p: Problem) -> list[list[Stop]]:
    """Parallel savings: start with one route per stop, merge route ends in order of savings s(i,j) = d(0,i) + d(0,j) - d(i,j)."""
    routes: dict[int, list[Stop]] = {i: [s] for i, s in enumerate(p.stops)}
    owner = {s.id: i for i, s in enumerate(p.stops)}
    savings = []
    for i, a in enumerate(p.stops):
        for b in p.stops[i + 1:]:
            savings.append((dist(p.depot, a) + dist(p.depot, b) - dist(a, b), a.id, b.id, a, b))
    savings.sort(key=lambda t: (-t[0], t[1], t[2]))

    for s, _, _, a, b in savings:
        if s <= 0:
            break
        ra, rb = owner[a.id], owner[b.id]
        if ra == rb:
            continue
        r1, r2 = routes[ra], routes[rb]
        # a and b must both be route ends (adjacent to the depot) to link them.
        if r1[-1] is not a:
            r1 = r1[::-1]
        if r2[0] is not b:
            r2 = r2[::-1]
        if r1[-1] is not a or r2[0] is not b:
            continue
        merged = r1 + r2
        if load(merged) > p.capacity or route_km(p.depot, merged) > p.max_route_km:
            continue
        routes[ra] = merged
        del routes[rb]
        for st in r2:
            owner[st.id] = ra
    return [routes[k] for k in sorted(routes)]


def two_opt(depot: Stop, route: list[Stop]) -> list[Stop]:
    """Reverse segments while it shortens the route (first-improvement). Removes crossing edges."""
    best = list(route)
    improved = True
    while improved:
        improved = False
        path = [depot, *best, depot]
        for i in range(1, len(path) - 2):
            for j in range(i + 1, len(path) - 1):
                delta = (dist(path[i - 1], path[j]) + dist(path[i], path[j + 1])) - (dist(path[i - 1], path[i]) + dist(path[j], path[j + 1]))
                if delta < -1e-9:
                    path[i:j + 1] = path[i:j + 1][::-1]
                    improved = True
        best = path[1:-1]
    return best


@dataclass(frozen=True)
class Solution:
    method: str
    routes: tuple[tuple[Stop, ...], ...]
    km: float
    trucks: int

    def cost(self, per_km: float, per_truck: float) -> float:
        return self.km * per_km + self.trucks * per_truck


def solve(p: Problem, method: str = "savings+2opt") -> Solution:
    if method == "nearest":
        routes = nearest_neighbour(p)
    elif method == "nearest+2opt":
        routes = [two_opt(p.depot, r) for r in nearest_neighbour(p)]
    elif method == "savings":
        routes = clarke_wright(p)
    elif method == "savings+2opt":
        routes = [two_opt(p.depot, r) for r in clarke_wright(p)]
    else:
        raise ValueError(f"unknown method {method}")
    return Solution(method, tuple(tuple(r) for r in routes), sum(route_km(p.depot, r) for r in routes), len(routes))


def check(p: Problem, sol: Solution) -> list[str]:
    """Independent feasibility check: every stop exactly once, capacity and route length respected."""
    problems = []
    seen = [s.id for r in sol.routes for s in r]
    if sorted(seen) != sorted(s.id for s in p.stops):
        problems.append("stops missing or visited twice")
    for i, r in enumerate(sol.routes, 1):
        if load(list(r)) > p.capacity:
            problems.append(f"route {i} over capacity: {load(list(r))} > {p.capacity}")
        if route_km(p.depot, list(r)) > p.max_route_km + 1e-9:
            problems.append(f"route {i} too long")
    return problems
