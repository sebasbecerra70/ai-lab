"""CLI: python -m ticket_routing ["ticket text" ...]"""
import sys
from pathlib import Path

from . import CentroidRouter, keyword_route, load, metrics, sweep

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    train, test = load(DATA / "train.csv"), load(DATA / "test.csv")
    router = CentroidRouter().fit([r["text"] for r in train], [r["queue"] for r in train])

    if sys.argv[1:]:
        for text in sys.argv[1:]:
            r = router.route(text)
            why = r.reason or "matched on " + ", ".join(router.explain(text, r.queue))
            print(f"{r.queue:<9} score {r.score:.2f} margin {r.margin:.2f}  ({why})  <- {text}")
        return

    truth = [r["queue"] for r in test]
    n_off = truth.count("triage")
    print(f"train {len(train)} tickets, test {len(test)} ({n_off} off-topic, half the rest use unseen phrasings)\n")
    print(f"{'router':<20}{'auto-routed':>12}{'acc routed':>12}{'end-to-end':>12}{'misroutes':>11}{'off-topic caught':>18}")
    for name, preds in (("keyword rules", [keyword_route(r["text"]) for r in test]),
                        ("tf-idf centroid", [router.route(r["text"]).queue for r in test])):
        m = metrics(preds, truth)
        print(f"{name:<20}{m.auto_rate:>12.0%}{m.routed_accuracy:>12.0%}{m.end_to_end:>12.0%}{m.misroutes:>11}{m.off_topic_caught:>18.0%}")

    print("\nthreshold sweep (min similarity): fewer misroutes cost more human triage")
    for th, m in sweep(router, test, [0.0, 0.06, 0.12, 0.18, 0.24, 0.30]):
        print(f"  {th:.2f}  auto {m.auto_rate:>4.0%}  misroutes {m.misroutes:>2}  off-topic caught {m.off_topic_caught:>4.0%}")

    print("\nsample decisions")
    for text in ["clicked a link in an email and now outlook is acting weird",
                 "VPN says my account is not authorized",
                 "the coffee machine on the 3rd floor is broken",
                 "my laptop screen is flickering after the update"]:
        r = router.route(text)
        why = r.reason or "matched on " + ", ".join(router.explain(text, r.queue))
        print(f"  {r.queue:<9} {r.score:.2f}/{r.margin:+.2f}  {text}  ({why})")


if __name__ == "__main__":
    main()
