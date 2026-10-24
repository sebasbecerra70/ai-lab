"""CLI: python -m reorder_agent"""
import json
import os
from pathlib import Path

from . import AnthropicLLM, MockLLM, ReorderAgent, eoq, load_items, reorder_point, safety_stock

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    items = load_items(DATA / "skus.csv")
    policy = json.loads((DATA / "policy.json").read_text())
    print(f"{'sku':<10}{'position':>9}{'safety':>8}{'ROP':>7}{'EOQ':>7}{'cover d':>9}{'LT d':>6}  status")
    for it in items:
        rop = reorder_point(it)
        status = "REORDER" if it.position <= rop else ""
        print(f"{it.sku:<10}{it.position:>9}{safety_stock(it):>8.0f}{rop:>7.0f}{eoq(it):>7.0f}"
              f"{it.position / it.daily_demand:>9.1f}{it.lead_time_days:>6.0f}  {status}")

    llm = AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else MockLLM()
    pos = ReorderAgent(items, policy, llm).run()
    print(f"\nproposed POs ({type(llm).__name__} memos):")
    for po in pos:
        print(f"\n{po.supplier}: ${po.value:,.2f} -> {po.status}")
        for l in po.lines:
            print(f"  {l.item.sku:<10} {l.qty:>5} x ${l.item.unit_cost:<7.2f} = ${l.value:>9,.2f}  {l.reason}{'  [EXPEDITE]' if l.expedite else ''}")
        for f in po.flags:
            print(f"  ! {f}")
        print(f"  memo: {po.memo}")
    auto = sum(po.value for po in pos if po.status == "submitted")
    pending = sum(po.value for po in pos if po.status.startswith("pending"))
    print(f"\nauto-submitted ${auto:,.2f}; awaiting approval ${pending:,.2f}; on hold {sum(po.status == 'hold' for po in pos)} PO(s)")


if __name__ == "__main__":
    main()
