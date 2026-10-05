"""CLI: python -m dock_scheduler [appointments.csv]"""
import sys
from pathlib import Path

from . import greedy, kpis, load_doors, load_trucks, local_search, rotation
from .report import door_table, kpi_table


def main() -> None:
    data = Path(__file__).resolve().parent.parent / "data"
    doors = load_doors(data / "doors.csv")
    trucks = load_trucks(Path(sys.argv[1]) if len(sys.argv) > 1 else data / "appointments.csv")
    by_name = {d.name: d for d in doors}
    base, g = rotation(trucks, doors), greedy(trucks, doors)
    best, history = local_search(g, doors)
    print(f"{len(trucks)} trucks, {len(doors)} doors ({sum(d.reefer for d in doors)} reefer)\n")
    rows = [("rotation", kpis(base, by_name)), ("greedy", kpis(g, by_name)), ("local search", kpis(best, by_name))]
    print(kpi_table(rows))
    print(f"\nlocal search cost path: {' -> '.join(f'{c:.0f}' for c in history)}")
    print("\nDoor plan after local search (* reefer, +N = minutes waited)")
    print(door_table(best, by_name))
    saved = rows[0][1].detention - rows[2][1].detention
    print(f"\ndetention saved vs rotation: ${saved:,.0f} today, ~${saved * 250:,.0f} over 250 shifts")


if __name__ == "__main__":
    main()
