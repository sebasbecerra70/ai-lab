"""CLI: python -m slotting"""
from pathlib import Path

from . import (Layout, abc_classes, abc_summary, apply_top_moves, assign_slots, evaluate, load_orders,
               load_skus, load_slotting, pick_velocity, prioritized_moves, validate)

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    skus, orders = load_skus(DATA / "skus.csv"), load_orders(DATA / "order_lines.csv")
    current = load_slotting(DATA / "current_slots.csv")
    velocity = pick_velocity(orders, skus)
    classes = abc_classes(velocity)
    n_lines = sum(velocity.values())
    print(f"{len(skus)} SKUs, {len(orders)} orders, {n_lines} pick lines\n")
    print("ABC velocity")
    for cls, (count, share) in abc_summary(velocity, classes).items():
        print(f"  {cls}: {count:>2} SKUs ({count / len(skus):4.0%}) -> {share:5.1%} of picks")

    target = assign_slots(skus, velocity, Layout())
    assert not validate(target, skus)
    before, after = evaluate(orders, current), evaluate(orders, target)
    print(f"\n{'slotting':<14}{'hours':>7}{'s/order':>9}{'s/line':>8}")
    for name, r in (("current", before), ("optimized", after)):
        print(f"{name:<14}{r.total_hours:>7.1f}{r.sec_per_order:>9.1f}{r.sec_per_line:>8.1f}")
    print(f"travel reduction: {1 - after.total_hours / before.total_hours:.1%}")

    moves = prioritized_moves(current, target, velocity)
    print(f"\n{len(moves)} moves for the full re-slot; phased plan:")
    for k in (5, 10, 20, len(moves)):
        r = evaluate(orders, apply_top_moves(current, moves, k))
        print(f"  top {k:>2} moves -> {1 - r.total_hours / before.total_hours:5.1%} less travel")
    print("\nfirst moves:")
    for m in moves[:5]:
        print(f"  {m.sku} [{classes[m.sku]}] {velocity[m.sku]:>3} picks  "
              f"A{m.old.aisle}-B{m.old.bay}-L{m.old.level} -> A{m.new.aisle}-B{m.new.bay}-L{m.new.level}")


if __name__ == "__main__":
    main()
