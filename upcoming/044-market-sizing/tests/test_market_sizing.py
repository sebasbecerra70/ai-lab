import json
import shutil
from pathlib import Path

import pytest

from market_sizing import Segment, bottom_up, load, reconcile, segment_value, top_down, tornado, two_way

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def m():
    return load(DATA)


def test_segment_value_is_sites_times_fit_times_racks_times_price():
    s = Segment("X", "colocation", facilities=100, racks_per_site=500, fit=0.5)
    assert segment_value(s, 60) == 100 * 0.5 * 500 * 60


def test_top_down_chain(m):
    td = top_down(m)
    assert td.tam == pytest.approx(3.1e9 * 0.07)
    assert td.sam == pytest.approx(td.tam * 0.68 * 0.70)


def test_bottom_up_sam_only_counts_served_segments(m):
    bu = bottom_up(m)
    served = sum(segment_value(s, 60) for s in m.segments
                 if s.region in {"North America", "Europe"} and s.tier in {"colocation", "enterprise"})
    assert bu.sam == pytest.approx(served)
    assert bu.sam < bu.tam


def test_som_is_the_smaller_of_sales_capacity_and_share_cap(m):
    bu = bottom_up(m)
    assert bu.som_binding == "sales capacity"
    assert bu.som < bu.sam * 0.08
    # with an enormous sales team, the market-share ceiling takes over
    big = bottom_up(m, {"reps": 500})
    assert big.som_binding == "market share"
    assert big.som == pytest.approx(big.sam * 0.08)


def test_sample_estimates_reconcile_within_tolerance(m):
    rec = reconcile(top_down(m), bottom_up(m))
    assert rec["tam"]["ok"] and rec["sam"]["ok"]
    assert 0.10 < rec["tam"]["gap"] < 0.20


def test_reconcile_flags_a_bad_top_down_assumption(m):
    rec = reconcile(top_down(m, {"capacity_planning_share": 0.30}), bottom_up(m))
    assert not rec["tam"]["ok"]


def test_tornado_ranks_go_to_market_levers_first_and_drops_flat_inputs(m):
    base, bars = tornado(m)
    assert base == pytest.approx(bottom_up(m).som)
    assert {b.name for b in bars[:2]} == {"reps", "deals_per_rep_per_year"}
    assert all(b.swing > 0 for b in bars)
    assert "global_dcim_spend" not in {b.name for b in bars}  # top-down input can't move bottom-up SOM
    assert [b.swing for b in bars] == sorted((b.swing for b in bars), reverse=True)


def test_two_way_grid_is_monotonic_in_price_and_productivity(m):
    rows, cols, table = two_way(m, "price_per_rack", "deals_per_rep_per_year")
    assert rows[0] == 45 and rows[-1] == 80 and len(cols) == 3
    for line in table:
        assert line == sorted(line)
    for c in range(3):
        assert [line[c] for line in table] == sorted(line[c] for line in table)


def test_load_rejects_base_outside_range(tmp_path):
    shutil.copy(DATA / "segments.csv", tmp_path / "segments.csv")
    cfg = json.loads((DATA / "assumptions.json").read_text())
    cfg["assumptions"]["price_per_rack"]["base"] = 200
    (tmp_path / "assumptions.json").write_text(json.dumps(cfg))
    with pytest.raises(ValueError, match="price_per_rack"):
        load(tmp_path)
