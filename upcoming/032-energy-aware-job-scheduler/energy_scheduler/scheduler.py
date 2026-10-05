"""Deadline-aware scheduling of batch jobs against hourly price and carbon signals.

Objective per hour = energy cost ($) + carbon_price * emissions (t CO2).
A carbon price of $0 optimizes cost only; a high carbon price optimizes carbon.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import GridHour, Job


class InfeasibleError(RuntimeError):
    pass


@dataclass
class Schedule:
    hours: dict[str, list[int]] = field(default_factory=dict)  # job_id -> hours it runs

    def load_kw(self, jobs: list[Job], horizon: int) -> list[float]:
        by_id = {j.job_id: j for j in jobs}
        load = [0.0] * horizon
        for jid, hrs in self.hours.items():
            for h in hrs:
                load[h] += by_id[jid].power_kw
        return load


def hour_score(g: GridHour, carbon_price_per_t: float) -> float:
    """Cost in $ of running 1 MWh in this hour, including the shadow carbon price."""
    return g.price_usd_mwh + carbon_price_per_t * g.carbon_g_kwh / 1000  # g/kWh == kg/MWh -> t/MWh /1000


def _fits(hours: list[int], power: float, load: list[float], cap_kw: float) -> bool:
    return all(load[h] + power <= cap_kw + 1e-9 for h in hours)


def schedule_asap(jobs: list[Job], grid: list[GridHour], cap_kw: float = float("inf")) -> Schedule:
    """Baseline: every job starts at its release hour (or the first hour with capacity)."""
    load, sched = [0.0] * len(grid), Schedule()
    for job in sorted(jobs, key=lambda j: (j.release_h, j.deadline_h)):
        for start in range(job.release_h, job.deadline_h - job.duration_h + 1):
            hrs = list(range(start, start + job.duration_h))
            if _fits(hrs, job.power_kw, load, cap_kw):
                break
        else:
            raise InfeasibleError(f"{job.job_id} cannot run before its deadline")
        for h in hrs:
            load[h] += job.power_kw
        sched.hours[job.job_id] = hrs
    return sched


def schedule_optimized(jobs: list[Job], grid: list[GridHour], cap_kw: float = float("inf"),
                       carbon_price_per_t: float = 0.0) -> Schedule:
    """Greedy: place least-flexible jobs first into their cheapest feasible hours.

    Non-preemptible jobs get the cheapest contiguous window; preemptible jobs get the
    cheapest individual hours in their release/deadline window.
    """
    score = [hour_score(g, carbon_price_per_t) for g in grid]
    load, sched = [0.0] * len(grid), Schedule()
    for job in sorted(jobs, key=lambda j: (j.slack, -j.energy_mwh)):
        window = range(job.release_h, min(job.deadline_h, len(grid)))
        if job.preemptible:
            free = [h for h in window if load[h] + job.power_kw <= cap_kw + 1e-9]
            if len(free) < job.duration_h:
                raise InfeasibleError(f"{job.job_id}: only {len(free)} free hours, needs {job.duration_h}")
            hrs = sorted(sorted(free, key=lambda h: (score[h], h))[: job.duration_h])
        else:
            best = None
            for start in range(job.release_h, job.deadline_h - job.duration_h + 1):
                cand = list(range(start, start + job.duration_h))
                if cand[-1] >= len(grid) or not _fits(cand, job.power_kw, load, cap_kw):
                    continue
                cost = sum(score[h] for h in cand)
                if best is None or cost < best[0]:
                    best = (cost, cand)
            if best is None:
                raise InfeasibleError(f"{job.job_id} has no feasible contiguous window")
            hrs = best[1]
        for h in hrs:
            load[h] += job.power_kw
        sched.hours[job.job_id] = hrs
    return sched


@dataclass
class Metrics:
    cost_usd: float
    carbon_kg: float
    peak_kw: float
    deadlines_met: bool


def evaluate(sched: Schedule, jobs: list[Job], grid: list[GridHour]) -> Metrics:
    cost = carbon = 0.0
    ok = True
    for job in jobs:
        hrs = sched.hours[job.job_id]
        ok &= len(hrs) == job.duration_h and min(hrs) >= job.release_h and max(hrs) < job.deadline_h
        if not job.preemptible:
            ok &= hrs == list(range(hrs[0], hrs[0] + job.duration_h))
        for h in hrs:
            mwh = job.power_kw / 1000
            cost += mwh * grid[h].price_usd_mwh
            carbon += mwh * grid[h].carbon_g_kwh  # MWh * kg/MWh
    return Metrics(cost, carbon, max(sched.load_kw(jobs, len(grid))), ok)


def tradeoff_curve(jobs: list[Job], grid: list[GridHour], cap_kw: float,
                   carbon_prices=(0, 50, 100, 200, 500)) -> list[tuple[float, Metrics]]:
    return [(cp, evaluate(schedule_optimized(jobs, grid, cap_kw, cp), jobs, grid)) for cp in carbon_prices]


def gantt(sched: Schedule, jobs: list[Job], horizon: int) -> str:
    lines = []
    for job in jobs:
        run = set(sched.hours[job.job_id])
        bar = "".join("#" if h in run else ("." if job.release_h <= h < job.deadline_h else " ")
                      for h in range(horizon))
        lines.append(f"{job.job_id:<18}|{bar}|")
    return "\n".join(lines)
