import json
from dataclasses import replace
from pathlib import Path

import pytest

from reorder_agent import (Item, MockLLM, ReorderAgent, annual_cost, eoq, load_items, plan_line, reorder_point, round_to_pack,
                           route, safety_stock, ungrounded_numbers, z_for_service_level)

DATA = Path(__file__).resolve().parent.parent / "data"
POLICY = json.loads((DATA / "policy.json").read_text())


def item(**kw):
    base = dict(sku="X", description="widget", supplier="Acme", unit_cost=10.0, on_hand=100, on_order=0, daily_demand=10.0,
                demand_std=0.0, lead_time_days=10, lead_time_std=0.0, order_cost=50, holding_rate=0.25, case_pack=1, service_level=0.95)
    base.update(kw)
    return Item(**base)


class Fixed:
    def __init__(self, text):
        self.text = text

    def complete(self, system, prompt):
        return self.text


def test_z_values_match_normal_table():
    assert z_for_service_level(0.95) == pytest.approx(1.6449, abs=1e-4)
    assert z_for_service_level(0.98) == pytest.approx(2.0537, abs=1e-4)


def test_safety_stock_zero_without_variability_and_grows_with_lead_time_risk():
    assert safety_stock(item()) == 0
    assert reorder_point(item()) == 100
    assert safety_stock(item(lead_time_std=3)) > safety_stock(item(demand_std=3))  # LT variance hits harder at d=10


def test_eoq_minimises_annual_cost():
    it = item()
    q = eoq(it)  # sqrt(2 * 3650 * 50 / 2.5) = 382.1
    assert q == pytest.approx(382.1, abs=0.1)
    assert annual_cost(it, q) < annual_cost(it, q * 0.7) and annual_cost(it, q) < annual_cost(it, q * 1.3)


def test_round_to_pack_never_returns_less_than_one_pack():
    assert round_to_pack(1, 24) == 24
    assert round_to_pack(49, 24) == 72


def test_no_order_above_reorder_point():
    assert plan_line(item(on_hand=101), 120) is None


def test_order_up_to_rop_plus_eoq_and_expedite_flag():
    line = plan_line(item(on_hand=50), 120)
    assert line.qty == round_to_pack(100 + eoq(item()) - 50, 1)
    assert line.expedite  # 5 days of cover vs 10-day lead time


def test_days_of_supply_cap():
    line = plan_line(item(on_hand=0, unit_cost=0.1), max_days_of_supply=30)  # cheap item -> huge EOQ
    assert line.capped and line.qty == 300


def test_approval_routing_tiers():
    tiers = POLICY["approval_tiers"]
    assert [route(v, tiers) for v in (4999, 5000.01, 25000, 25000.01)] == ["auto", "ops_manager", "ops_manager", "director"]


def test_top_up_pulls_forward_nearby_items_to_hit_supplier_minimum():
    items = [item(sku="A", on_hand=95, unit_cost=0.1), item(sku="B", on_hand=105, unit_cost=5.0), item(sku="C", on_hand=900)]
    pos = ReorderAgent(items, {**POLICY, "supplier_min_order_value": {"Acme": 1000}}, MockLLM()).run()
    skus = [l.item.sku for l in pos[0].lines]
    assert skus == ["A", "B"]  # C is ~80 days from its ROP, too early to pull forward
    assert pos[0].status == "submitted"


def test_po_below_minimum_is_held():
    pos = ReorderAgent([item(on_hand=95, unit_cost=1.0)], {**POLICY, "supplier_min_order_value": {"Acme": 10_000}}, MockLLM()).run()
    assert pos[0].status == "hold"
    assert any("below supplier minimum" in f for f in pos[0].flags)


def test_memo_with_invented_numbers_is_replaced():
    it = item(on_hand=50)
    pos = ReorderAgent([it], POLICY, Fixed("Supplier says price rises 12% next week, buy 900 now.")).run()
    assert any("ungrounded" in f for f in pos[0].flags)
    assert "900" not in pos[0].memo
    assert ungrounded_numbers("PO value $1,234.50 for 3 lines", {"po_value": 1234.5, "line_count": 3}) == []


def test_sample_run_routes_every_po():
    pos = ReorderAgent(load_items(DATA / "skus.csv"), POLICY, MockLLM()).run()
    status = {po.supplier: po.status for po in pos}
    assert status["Motion Industrial"] == "pending director"
    assert status["Lubricant Depot"] == "submitted"
    assert "GLV-NIT-L" in [l.item.sku for po in pos for l in po.lines]  # pulled forward for Safety First's minimum
    assert all(not any("ungrounded" in f for f in po.flags) for po in pos)
