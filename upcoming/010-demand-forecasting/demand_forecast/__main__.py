"""CLI: python -m demand_forecast   backtest every model on every SKU and pick a winner per SKU."""
from pathlib import Path

from . import default_models, evaluate, intermittency, load_series


def _pct(x):
    return "   n/a" if x is None else f"{x:6.1%}"


def main() -> None:
    series = load_series(Path(__file__).resolve().parent.parent / "data" / "weekly_demand.csv")
    models = default_models()
    print("Rolling-origin backtest: 20 origins x 4-week horizon (last 80 weeks)\n")
    for sku, y in series.items():
        adi = intermittency(y)
        kind = "intermittent" if adi > 1.32 else "smooth"
        rank_by = "WAPE-4wk" if kind == "intermittent" else "weekly WAPE"
        print(f"{sku}  ({len(y)} weeks, mean {sum(y) / len(y):.1f}/wk, ADI {adi:.2f} -> {kind}, ranked by {rank_by})")
        print(f"    {'model':<16}{'WAPE':>7}{'MAPE':>8}{'bias':>8}{'WAPE-4wk':>10}")
        scores = evaluate(y, models)
        for i, s in enumerate(scores):
            mark = "  <- best" if i == 0 else ""
            print(f"    {s.model:<16}{s.wape:7.1%}{_pct(s.mape):>8}{s.bias:+8.1%}{s.wape_horizon:10.1%}{mark}")
        print()


if __name__ == "__main__":
    main()
