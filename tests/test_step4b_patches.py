"""Engine/classifier patches that came out of real-page extraction."""
from rbi_tracker.engine import compare
from rbi_tracker.engine.models import Release
from rbi_tracker.fetch.classify import default_classifier


def tb(date, notified, accepted, total):
    return Release("tbill_result", date, "ref", "", {}, [
        {"key": "91D", "notified_amount": notified, "accepted_amount": accepted, "total_allotment_amount": total,
         "cutoff_yield": 5.8, "bid_cover": 3.0}], {})


def test_tbill_total_allotment_is_judged_against_notified():
    # competitive 7,600 < notified 8,000 but total allotment 8,600 > notified: not under-accepted
    d = compare(tb("2026-11-11", 8000, 7600, 8600), tb("2026-11-04", 8000, 8000, 8000), None)
    flags = [c for c in d.changes if c.metric == "accepted_vs_notified"]
    assert flags and not flags[0].priority and "above notified" in flags[0].note


def test_tbill_total_below_notified_is_priority():
    d = compare(tb("2026-11-11", 8000, 7000, 7500), None, None)
    flags = [c for c in d.changes if c.metric == "accepted_vs_notified"]
    assert flags and flags[0].priority


def bop(period, ytd, ca, ytd_ca):
    return Release("bop", "2026-11-13", "ref", "", {"period": period, "ytd_period": ytd,
                                                    "current_account_balance": ca, "ytd_current_account_balance": ytd_ca},
                   [], {"current_account_balance": -1.0, "ytd_current_account_balance": -2.0})


def test_bop_ytd_compared_within_same_year_and_labelled():
    d = compare(bop("Sep 2026", "April-September 2026", -7.4, -25.8),
                bop("Jun 2026", "April-June 2026", -3.0, -10.0), None)
    notes = " ".join(c.note for c in d.changes)
    assert "year to date" in notes


def test_bop_ytd_not_compared_across_years():
    d = compare(bop("Jun 2027", "April-June 2027", -3.0, -10.0),
                bop("Mar 2027", "April-March 2027", -5.0, -40.0), None)
    prior = [c for c in d.changes if "year to date" in c.note and "prior period" in c.note]
    assert not prior and any("Year-to-date figures not compared" in i for i in d.info)


def test_classifier_detects_omo_result_title():
    c = default_classifier()
    assert c.classify("Detailed Result: OMO Sale Auction held on Oct 13, 2026 and Settlement on Oct 14") == "omo_result"