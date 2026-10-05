"""Reorder agent: decide what to buy, group into POs, top up to supplier minimums, route for approval, write memos.

The math and the approval routing are deterministic code. The LLM only writes the approver memo, and the memo is
checked so it can't introduce numbers that aren't in the facts.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

from .calc import Item, eoq, reorder_point, round_to_pack, safety_stock
from .llm import LLMClient

MEMO_SYSTEM = (
    "You write purchase-order approval memos for an MRO storeroom. In 2-3 sentences, tell the approver why this PO is "
    "needed now and what happens if it is delayed. Use ONLY numbers from the FACTS JSON. Mention expedite flags first."
)


@dataclass
class Line:
    item: Item
    qty: int
    reason: str
    rop: float
    expedite: bool = False
    capped: bool = False

    @property
    def value(self) -> float:
        return round(self.qty * self.item.unit_cost, 2)


@dataclass
class PurchaseOrder:
    supplier: str
    lines: list[Line] = field(default_factory=list)
    approver: str = ""
    status: str = ""
    memo: str = ""
    flags: list[str] = field(default_factory=list)

    @property
    def value(self) -> float:
        return round(sum(l.value for l in self.lines), 2)


def plan_line(it: Item, max_days_of_supply: float) -> Line | None:
    """(s, S) policy: when inventory position is at or below the reorder point, order up to ROP + EOQ."""
    rop = reorder_point(it)
    if it.position > rop:
        return None
    target = rop + eoq(it)
    qty = round_to_pack(target - it.position, it.case_pack)
    ceiling = max_days_of_supply * it.daily_demand - it.position
    capped = qty > ceiling >= it.case_pack
    if capped:
        qty = max(it.case_pack, math.floor(ceiling / it.case_pack) * it.case_pack)
    # Open orders are assumed to land within the lead time, so cover counts on-hand plus on-order.
    cover = it.position / it.daily_demand if it.daily_demand else math.inf
    return Line(it, qty, f"position {it.position} <= ROP {rop:.0f}", rop, expedite=cover < it.lead_time_days, capped=capped)


def route(value: float, tiers: list[dict]) -> str:
    for t in tiers:
        if t["max_value"] is None or value <= t["max_value"]:
            return t["approver"]
    raise ValueError("approval tiers must end with an open-ended tier")


def memo_facts(po: PurchaseOrder) -> dict:
    return {
        "supplier": po.supplier,
        "po_value": po.value,
        "approver": po.approver,
        "line_count": len(po.lines),
        "flags": po.flags,
        "lines": [{
            "sku": l.item.sku, "description": l.item.description, "qty": l.qty, "value": l.value,
            "position": l.item.position, "days_of_cover": round(l.item.position / l.item.daily_demand, 1),
            "lead_time_days": l.item.lead_time_days, "reorder_point": round(l.rop), "reason": l.reason, "expedite": l.expedite,
        } for l in po.lines],
    }


def ungrounded_numbers(memo: str, facts: dict) -> list[str]:
    """Numbers in the memo that do not appear in the facts (after stripping $ and thousands separators)."""
    known = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(facts)))
    known |= {k.rstrip("0").rstrip(".") for k in known if "." in k}
    found = [n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", memo)]
    return sorted({n for n in found if n not in known and n.rstrip("0").rstrip(".") not in known})


class ReorderAgent:
    def __init__(self, items: list[Item], policy: dict, llm: LLMClient):
        self.items = items
        self.policy = policy
        self.llm = llm

    def run(self) -> list[PurchaseOrder]:
        max_dos = self.policy.get("max_days_of_supply", 120)
        by_supplier: dict[str, PurchaseOrder] = defaultdict(lambda: PurchaseOrder(""))
        for it in self.items:
            line = plan_line(it, max_dos)
            if line:
                po = by_supplier[it.supplier]
                po.supplier = it.supplier
                po.lines.append(line)

        pos = []
        for supplier, po in sorted(by_supplier.items()):
            self._top_up(po, max_dos)
            if any(l.expedite for l in po.lines):
                po.flags.append("expedite: " + ", ".join(l.item.sku for l in po.lines if l.expedite) + " will run out before a standard delivery")
            if any(l.capped for l in po.lines):
                po.flags.append(f"capped at {max_dos} days of supply: " + ", ".join(l.item.sku for l in po.lines if l.capped))
            po.approver = route(po.value, self.policy["approval_tiers"])
            minimum = self.policy["supplier_min_order_value"].get(supplier, 0)
            if po.value < minimum:
                po.flags.append(f"below supplier minimum ${minimum:,.0f}")
                po.status = "hold"
            else:
                po.status = "submitted" if po.approver == "auto" else f"pending {po.approver}"
            facts = memo_facts(po)
            po.memo = self.llm.complete(MEMO_SYSTEM, "FACTS:\n" + json.dumps(facts))
            bad = ungrounded_numbers(po.memo, facts)
            if bad:
                po.flags.append(f"memo had ungrounded numbers {bad}; replaced with template")
                po.memo = template_memo(facts)
            pos.append(po)
        return pos

    def _top_up(self, po: PurchaseOrder, max_dos: float) -> None:
        """Below the supplier minimum? Pull forward same-supplier items that will hit their ROP soonest."""
        minimum = self.policy["supplier_min_order_value"].get(po.supplier, 0)
        ordered = {l.item.sku for l in po.lines}
        candidates = sorted(
            (it for it in self.items if it.supplier == po.supplier and it.sku not in ordered),
            key=lambda it: (it.position - reorder_point(it)) / it.daily_demand,  # days until it reaches ROP
        )
        for it in candidates:
            if po.value >= minimum:
                return
            days_to_rop = (it.position - reorder_point(it)) / it.daily_demand
            if days_to_rop > 30:
                return  # don't buy a month+ early just to hit a minimum
            qty = round_to_pack(eoq(it), it.case_pack)
            po.lines.append(Line(it, qty, f"pulled forward: reaches ROP in {days_to_rop:.1f} days", reorder_point(it)))


def template_memo(f: dict) -> str:
    urgent = [l for l in f["lines"] if l["expedite"]]
    lead = (f"Expedite {', '.join(l['sku'] for l in urgent)}: stock on hand and on order covers {urgent[0]['days_of_cover']} "
            f"days against a {urgent[0]['lead_time_days']:g}-day lead time. ") if urgent else ""
    worst = min(f["lines"], key=lambda l: l["days_of_cover"])
    return (f"{lead}{f['line_count']} line(s) from {f['supplier']} totalling ${f['po_value']:,.2f}; "
            f"{worst['sku']} ({worst['description']}) is lowest at {worst['days_of_cover']} days of cover. "
            f"Delaying risks a stockout on items at or below their reorder point.")


__all__ = ["Line", "PurchaseOrder", "ReorderAgent", "memo_facts", "plan_line", "route", "safety_stock", "template_memo",
           "ungrounded_numbers"]
