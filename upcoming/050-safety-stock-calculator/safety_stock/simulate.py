"""Monte Carlo check: run a continuous-review (ROP, Q) policy with random demand and lead times, and
measure the cycle service level and fill rate actually achieved."""
from __future__ import annotations

import random
from dataclasses import dataclass

from .model import Sku


@dataclass
class SimResult:
    cycles: int
    stockout_cycles: int
    demand: float
    short: float

    @property
    def csl(self) -> float:
        return 1 - self.stockout_cycles / max(self.cycles, 1)

    @property
    def fill_rate(self) -> float:
        return 1 - self.short / max(self.demand, 1e-9)


def simulate(s: Sku, rop: float, weeks: int = 20000, seed: int = 0, days_per_week: int = 7) -> SimResult:
    """Daily steps, backorders, reorder on inventory position (on hand + on order - backorders), so several
    orders can be in flight when Q is smaller than lead-time demand. A cycle = the time between two receipts;
    it counts as a stockout if any demand went unserved from the shelf during it."""
    rng = random.Random(seed)
    # Gamma draws match the observed mean and variance without the bias of a normal truncated at zero
    # (which inflates mean demand for slow movers), and give the right skew for lead times.
    mu, var = s.d / days_per_week, s.sd_d ** 2 / days_per_week
    d_shape, d_scale = mu * mu / var, var / mu
    lt_shape, lt_scale = s.lt ** 2 / s.sd_lt ** 2, s.sd_lt ** 2 / s.lt
    net = rop + s.order_qty          # on hand minus backorders
    pipeline: list[tuple[int, float]] = []
    cycles = stockouts = 0
    demand = short = 0.0
    short_this_cycle = False
    for day in range(weeks * days_per_week):
        arrived = [q for t, q in pipeline if t <= day]
        if arrived:
            pipeline = [(t, q) for t, q in pipeline if t > day]
            net += sum(arrived)
            cycles += 1
            stockouts += short_this_cycle
            short_this_cycle = False
        dem = rng.gammavariate(d_shape, d_scale)
        demand += dem
        unserved = dem - min(dem, max(net, 0.0))
        if unserved > 0:
            short += unserved
            short_this_cycle = True
        net -= dem
        while net + sum(q for _, q in pipeline) <= rop:
            lt_days = max(1, round(rng.gammavariate(lt_shape, lt_scale) * days_per_week))
            pipeline.append((day + lt_days, s.order_qty))
    return SimResult(cycles, stockouts, demand, short)
