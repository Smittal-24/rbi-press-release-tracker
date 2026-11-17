"""CG and SG results judge total allotment against notified."""
from rbi_tracker.engine import compare
from rbi_tracker.engine.models import Release


def res(item, key, notified, accepted, total):
    return Release(item, "2026-11-13", "ref", "", {}, [
        {"key": key, "notified_amount": notified, "accepted_amount": accepted, "total_allotment_amount": total,
         "bid_cover": 2.0}], {})


def flags(d):
    return [c for c in d.changes if c.metric == "accepted_vs_notified"]


def test_cg_fully_allotted_is_not_flagged():
    # 13 Nov 2026 CG: competitive 33,947.718 of 34,000 notified; total allotment 34,000
    d = compare(res("cg_result", "10Y", 34000, 33947.718, 34000), None)
    assert not flags(d) and any("total allotment = notified" in u for u in d.unchanged)


def test_cg_real_shortfall_is_priority():
    d = compare(res("cg_result", "10Y", 34000, 30000, 31000), None)
    f = flags(d)
    assert f and f[0].priority and "total allotment" in f[0].note and "below notified" in f[0].note


def test_sg_shortfall_in_whole_auction_is_priority():
    # 9 Nov 2026 SG: notified 29,050, total allotment 27,083.882
    d = compare(res("sg_result", "ALL", 29050, 25921.784, 27083.882), None)
    f = flags(d)
    assert f and f[0].priority and f[0].delta == round(27083.882 - 29050, 2)


def test_missing_total_falls_back_to_accepted():
    d = compare(res("cg_result", "10Y", 8000, 7000, None), None)
    f = flags(d)
    assert f and "accepted" in f[0].note and f[0].priority