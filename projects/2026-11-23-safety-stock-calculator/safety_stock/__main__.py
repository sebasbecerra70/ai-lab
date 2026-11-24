"""CLI: python -m safety_stock [data_dir]"""
import sys
from pathlib import Path

from . import load, portfolio_value, reorder_point, safety_stock_csl, safety_stock_fill, simulate, tradeoff_curve

DATA = Path(__file__).resolve().parent.parent / "data"
TARGET = {"A": 0.98, "B": 0.95, "C": 0.90}


def main() -> None:
    skus = load(Path(sys.argv[1]) if len(sys.argv) > 1 else DATA)
    print(f"{len(skus)} SKUs, 52 weeks of demand, 10 receipts each; cycle-service targets {TARGET}\n")
    print(f"{'sku':<9}{'abc':<4}{'d/wk':>6}{'sd_d':>6}{'LT wk':>7}{'sd_LT':>6}{'LT var':>8}"
          f"{'SS naive':>10}{'SS':>7}{'ROP':>7}{'SS fill99':>10}{'SS $':>9}  {'simulated CSL':>13}")
    for s in skus:
        csl = TARGET[s.abc]
        ss = safety_stock_csl(s, csl)
        naive = ss / s.sigma_ltd * s.sigma_demand_only
        rop = reorder_point(s, ss)
        sim = simulate(s, rop, weeks=5000, seed=1)
        sim_naive = simulate(s, s.d * s.lt + naive, weeks=5000, seed=1)
        print(f"{s.sku:<9}{s.abc:<4}{s.d:>6.0f}{s.sd_d:>6.0f}{s.lt:>7.1f}{s.sd_lt:>6.1f}{s.lt_share:>8.0%}"
              f"{naive:>10.0f}{ss:>7.0f}{rop:>7.0f}{safety_stock_fill(s, 0.99):>10.0f}"
              f"{ss * s.unit_cost:>9,.0f}  {sim_naive.csl:>5.1%} -> {sim.csl:.1%}")
    print("\n'SS naive' ignores lead-time variability; 'LT var' = share of lead-time demand variance from the supplier.")
    print("simulated CSL: 5,000 weeks of gamma demand and lead times, naive SS -> full SS.")

    print("\nservice level vs safety stock investment (all SKUs at one cycle-service level)")
    for p in tradeoff_curve(skus, [0.80, 0.90, 0.95, 0.98, 0.99, 0.995, 0.999]):
        bar = "#" * int(p.value / 4000)
        extra = f"  +${p.marginal:,.0f}" if p.marginal else ""
        print(f"  {p.service:>6.1%}  ${p.value:>9,.0f}  {bar}{extra}")
    flat = portfolio_value(skus, {"A": 0.98, "B": 0.98, "C": 0.98})
    tiered = portfolio_value(skus, TARGET)
    print(f"\nflat 98% on every SKU: ${flat:,.0f}   ABC-tiered {TARGET['A']:.0%}/{TARGET['B']:.0%}/{TARGET['C']:.0%}: "
          f"${tiered:,.0f}  (saves ${flat - tiered:,.0f})")


if __name__ == "__main__":
    main()
