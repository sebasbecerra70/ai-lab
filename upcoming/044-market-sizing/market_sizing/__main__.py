"""CLI: python -m market_sizing [data_dir]"""
import sys
from pathlib import Path

from . import bottom_up, load, reconcile, top_down, tornado, two_way

DATA = Path(__file__).resolve().parent.parent / "data"


def usd(x: float) -> str:
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(x) >= div:
            return f"${x / div:,.1f}{suffix}"
    return f"${x:,.0f}"


def main() -> None:
    m = load(Path(sys.argv[1]) if len(sys.argv) > 1 else DATA)
    td, bu = top_down(m), bottom_up(m)
    print(m.product)
    print(f"serving {', '.join(sorted(m.served_regions))} / {', '.join(sorted(m.served_tiers))}\n")
    print(f"{'':10}{'top-down':>12}{'bottom-up':>12}{'gap':>7}")
    rec = reconcile(td, bu)
    for level in ("tam", "sam"):
        r = rec[level]
        print(f"{level.upper():10}{usd(r['top_down']):>12}{usd(r['bottom_up']):>12}{r['gap']:>6.0%}{'' if r['ok'] else '  <- check'}")
    print(f"{'SOM':10}{usd(td.som):>12}{usd(bu.som):>12}       bottom-up capped by {bu.som_binding}")
    print(f"(SOM = ARR after {m.values()['years']:.0f} years)")

    base, bars = tornado(m)
    print(f"\nTornado: bottom-up SOM {usd(base)}, each assumption at low / high")
    for b in bars:
        print(f"  {b.name:<24}{usd(b.low_value):>9} .. {usd(b.high_value):<9} swing {usd(b.swing)}")

    rows, cols, table = two_way(m, "price_per_rack", "deals_per_rep_per_year")
    print("\nSOM by price per rack (rows) x deals per rep per year (cols)")
    print(f"{'':>8}" + "".join(f"{c:>10.0f}" for c in cols))
    for r, line in zip(rows, table):
        print(f"{'$' + format(r, '.0f'):>8}" + "".join(f"{usd(v):>10}" for v in line))


if __name__ == "__main__":
    main()
