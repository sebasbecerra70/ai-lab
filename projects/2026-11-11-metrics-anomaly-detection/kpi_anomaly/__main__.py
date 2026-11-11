"""CLI: python -m kpi_anomaly [--threshold 3.5]"""
import argparse
from pathlib import Path

from . import decompose, detect, detect_naive, load_kpis, score

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=3.5)
    args = ap.parse_args()
    t = load_kpis(DATA / "kpis.csv")
    print(f"{len(t.days)} days x {len(t.series)} KPIs, {len(t.labels)} labeled anomalies (incl. downstream)\n")
    dau = decompose(t.series["dau"])
    print("weekly seasonality (dau): " + "  ".join(f"{d} {s:.2f}" for d, s in zip(t.weekdays[:7], dau.seasonal[:7])))

    found = detect(t, args.threshold)
    print(f"\nanomalies (|robust z| >= {args.threshold})")
    for a in found:
        why = f"  <- explained by {', '.join(a.explained_by)}" if a.explained_by else ""
        print(f"  day {a.day:>3} {t.weekdays[a.day - 1]}  {a.metric:<16}{a.pct_off:+7.1%} vs expected  z={a.z:+6.1f}{why}")

    ours = score({(a.day, a.metric) for a in found}, t.labels)
    naive = score(set(detect_naive(t)), t.labels)
    print(f"\n{'method':<28}{'precision':>10}{'recall':>8}")
    print(f"{'decomposition + robust z':<28}{ours.precision:>10.0%}{ours.recall:>8.0%}")
    print(f"{'naive z-score on raw values':<28}{naive.precision:>10.0%}{naive.recall:>8.0%}")
    roots = [a for a in found if not a.explained_by]
    print(f"\n{len(found)} flags -> {len(roots)} root-cause alerts after suppressing explained downstream moves")


if __name__ == "__main__":
    main()
