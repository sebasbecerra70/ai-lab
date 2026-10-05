"""CLI: python -m capacity_planner [horizon_months]"""
import sys
from pathlib import Path

from . import forecast, forecast_table, headroom_table, load_halls, load_scenarios, load_site


def main() -> None:
    data = Path(__file__).resolve().parent.parent / "data"
    horizon = int(sys.argv[1]) if len(sys.argv) > 1 else 36
    halls, site = load_halls(data / "halls.csv"), load_site(data / "site.json")
    print("Current headroom (usable = design x {:.0%} margin)".format(site.safety_margin))
    print(headroom_table(halls, site))
    print(f"\nForecast, {horizon}-month horizon")
    forecasts = [forecast(halls, site, s, horizon) for s in load_scenarios(data / "scenarios.json")]
    print(forecast_table(forecasts, horizon))


if __name__ == "__main__":
    main()
