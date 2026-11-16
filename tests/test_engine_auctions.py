import copy

import pytest

from rbi_tracker.engine import compare
from engine_data import *  # noqa: F401,F403


# ---------------- announcements ----------------
def test_announcement_amount_added_and_missing_tenors():
    d = compare(CG_ANN_NEW, CG_ANN_PREV)
    c = find(d, "notified_amount", "10Y")[0]
    assert (c.previous, c.new, c.delta, c.pct_change, c.unit) == (14000, 15000, 1000, 7.14, "Rs crore")
    assert find(d, "tenor_added", "30Y")[0].priority
    assert find(d, "tenor_missing", "5Y")[0].priority
    total = find(d, "total_notified_amount")[0]
    assert (total.previous, total.new, total.delta) == (38000, 35000, -3000)
    assert "CG 14Y notified amount" in d.unchanged       # flat items noted only briefly
    assert not find(d, "notified_amount", "14Y")          # ... and not listed as changes


def test_omo_direction_flip_is_priority():
    d = compare(OMO_ANN_NEW, OMO_ANN_PREV)
    c = find(d, "direction")[0]
    assert (c.previous, c.new, c.priority) == ("purchase", "sale", True)
    assert "flipped" in c.note


def test_identical_announcement_has_no_changes():
    d = compare(CG_ANN_PREV, copy.deepcopy(CG_ANN_PREV))
    assert d.changes == []
    assert d.unchanged


def test_announcement_without_previous():
    d = compare(CG_ANN_NEW, None)
    assert d.changes == [] and not d.has_previous
    assert "First recorded" in d.info[0]


# ---------------- results ----------------
def test_result_compares_same_tenor_only():
    d = compare(CG_RES_NEW, CG_RES_PREV)
    y = find(d, "cutoff_yield", "10Y")[0]
    assert (y.previous, y.new, y.delta, y.unit) == (6.52, 6.56, 4.0, "bps")
    assert "+4 bps" in y.note
    assert find(d, "bid_cover", "10Y")[0].delta == 0.21
    assert find(d, "accepted_amount", "10Y")[0].delta == 1000
    # 14Y did not move, even though 10Y did: tenors are independent
    assert not find(d, "cutoff_yield", "14Y")
    assert "CG 14Y cut-off yield" in d.unchanged


def test_tbill_tenors_move_independently():
    d = compare(TB_RES_NEW, TB_RES_PREV)
    assert find(d, "cutoff_yield", "91D")[0].delta == -2.0
    assert find(d, "cutoff_yield", "182D")[0].delta == 5.0


def test_vrrr_cutoff_rate_and_bid_cover():
    d = compare(VRRR_RES_NEW, VRRR_RES_PREV)
    assert find(d, "cutoff_rate", "14D")[0].delta == 1.0
    assert find(d, "bid_cover", "14D")[0].delta == 0.1


def test_omo_cutoff_price_absolute_change():
    d = compare(OMO_RES_NEW, OMO_RES_PREV)
    c = find(d, "cutoff_price", "10Y")[0]
    assert c.delta == 0.25 and c.unit == "Rs"


def test_result_vs_own_announcement_flags_shortfall_devolvement_and_undersubscription():
    ann = rel("cg_announcement", "2026-11-13", rows=[{"key": "10Y", "notified_amount": 14000}])
    res = rel("cg_result", "2026-11-14", rows=[
        {"key": "10Y", "accepted_amount": 12500, "cutoff_yield": 6.56, "bid_cover": 0.9, "devolvement_amount": 1500}])
    d = compare(res, None, announcement=ann)
    shortfall = find(d, "accepted_vs_notified", "10Y")[0]
    assert shortfall.priority and shortfall.delta == -1500 and shortfall.comparison == "announcement"
    assert find(d, "devolvement", "10Y")[0].new == 1500
    assert find(d, "undersubscribed", "10Y")[0].priority


def test_result_fully_accepted_is_unchanged_not_flagged():
    ann = rel("cg_announcement", "2026-11-13", rows=[{"key": "10Y", "notified_amount": 15000}])
    d = compare(CG_RES_NEW, CG_RES_PREV, announcement=ann)
    assert not find(d, "accepted_vs_notified", "10Y")
    assert "CG 10Y accepted = notified" in d.unchanged


def test_accepted_above_notified_is_noted_but_not_priority():
    ann = rel("tbill_announcement", "2026-11-10", rows=[{"key": "91D", "notified_amount": 8000}])
    res = rel("tbill_result", "2026-11-11", rows=[{"key": "91D", "accepted_amount": 8500, "bid_cover": 3.0}])
    c = find(compare(res, None, announcement=ann), "accepted_vs_notified", "91D")[0]
    assert c.delta == 500 and not c.priority


def test_new_tenor_in_result_has_no_prior_and_is_noted():
    res = rel("cg_result", "2026-11-14", rows=[{"key": "30Y", "accepted_amount": 8000, "cutoff_yield": 6.9}])
    d = compare(res, CG_RES_PREV)
    assert any("30Y" in line and "no previous result" in line for line in d.info)


# ---------------- guards ----------------
def test_mismatched_item_types_raise():
    with pytest.raises(ValueError):
        compare(CG_RES_NEW, TB_RES_PREV)


def test_wrong_announcement_family_raises():
    with pytest.raises(ValueError):
        compare(CG_RES_NEW, CG_RES_PREV, announcement=OMO_ANN_NEW)


def test_duplicate_keys_raise():
    bad = rel("cg_result", "2026-11-14", rows=[{"key": "10Y"}, {"key": "10Y"}])
    with pytest.raises(ValueError):
        compare(bad, CG_RES_PREV)


def test_unknown_item_raises():
    with pytest.raises(ValueError):
        compare(rel("nonsense", "2026-11-14"), None)


def test_accepts_plain_dicts_and_summary_lines():
    d = compare(CG_RES_NEW.to_dict(), CG_RES_PREV.to_dict())
    lines = d.summary_lines()
    assert any("cut-off yield" in line and "+4 bps" in line for line in lines)
    assert lines[-1].startswith("Unchanged:")
