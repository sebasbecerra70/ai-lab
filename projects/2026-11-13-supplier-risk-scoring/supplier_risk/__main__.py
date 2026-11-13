"""CLI: python -m supplier_risk"""
from pathlib import Path

from . import concentration, load_countries, load_scenarios, load_suppliers, run, score_all

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    suppliers, countries = load_suppliers(DATA / "suppliers.csv"), load_countries(DATA / "countries.csv")
    results = score_all(suppliers, countries)
    print(f"{'supplier':<31}{'ctry':<5}{'fin':>4}{'geo':>5}{'dlv':>5}{'risk':>6}  {'tier':<9}{'P(dis)':>7}{'exposure':>11}")
    for r in results:
        s = r.supplier
        print(f"{s.name[:30]:<31}{s.country:<5}{r.financial:>4.0f}{r.geo:>5.0f}{r.delivery:>5.0f}{r.composite:>6.1f}  "
              f"{r.tier:<9}{r.disruption_prob:>7.1%}{r.exposure_usd:>11,.0f}{'  single-source' if s.single_source else ''}")
    total = sum(r.exposure_usd for r in results)
    top3 = sum(r.exposure_usd for r in results[:3])
    print(f"\ntotal expected annual disruption cost ${total:,.0f}; top 3 suppliers = {top3 / total:.0%}")
    conc = concentration(suppliers)
    hhi = conc.pop("HHI")
    print("spend by country: " + ", ".join(f"{k} {v:.0%}" for k, v in sorted(conc.items(), key=lambda kv: -kv[1])[:4])
          + f"  (HHI {hhi:.2f})")

    print("\nwhat-if scenarios")
    for sc in load_scenarios(DATA / "scenarios.json"):
        imp = run(sc, suppliers, countries)
        delta = imp.total_exposure_after - imp.total_exposure_before
        print(f"- {sc.name}: exposure ${imp.total_exposure_before:,.0f} -> ${imp.total_exposure_after:,.0f} ({delta:+,.0f})")
        for name, before, after in imp.tier_changes:
            print(f"    {name}: {before} -> {after}")
        print(f"    biggest mover: {imp.top_movers[0][0]} ({imp.top_movers[0][1]:+,.0f})")


if __name__ == "__main__":
    main()
