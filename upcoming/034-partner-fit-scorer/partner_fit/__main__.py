"""CLI: python -m partner_fit"""
from pathlib import Path

from . import explain, load_config, load_partners, score, sensitivity

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    directions, ahp = load_config(DATA / "criteria.json")
    partners = load_partners(DATA / "partners.csv", list(directions))
    print("AHP weights (from 15 pairwise judgments)")
    for c, w in sorted(ahp.weights.items(), key=lambda kv: -kv[1]):
        print(f"  {c:<20} {w:6.1%}  {'#' * round(w * 60)}")
    status = "OK" if ahp.consistent else "REVISIT JUDGMENTS"
    print(f"  consistency ratio {ahp.consistency_ratio:.3f} ({status}, threshold 0.10)\n")

    ranked = score(partners, directions, ahp.weights)
    print(f"{'rank':<5}{'partner':<31}{'type':<12}{'fit':>5}  why")
    for i, s in enumerate(ranked, 1):
        print(f"{i:<5}{s.partner.name:<31}{s.partner.kind:<12}{s.score:>5.1f}  {explain(s)}")

    rows = sensitivity(partners, directions, ahp.weights)
    flips = [r for r in rows if r.leader_changed]
    print(f"\nrobustness: {ranked[0].partner.name} stays #1 in {len(rows) - len(flips)}/{len(rows)} "
          "single-weight shifts (±25%, ±50%)")
    for r in flips:
        print(f"  {r.criterion} {r.change:+.0%} -> {r.new_leader} leads")


if __name__ == "__main__":
    main()
