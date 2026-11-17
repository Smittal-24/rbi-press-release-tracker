"""Extractors run against real RBI pages saved in tests/fixtures/rbi (values checked by hand against the pages)."""
from pathlib import Path

import pytest

from rbi_tracker.extract.extract import extract
from rbi_tracker.extract.common import ExtractionError

FIX = Path(__file__).parent / "fixtures" / "rbi"


def run(item, prid, **kw):
    return extract(item, (FIX / f"{prid}.html").read_text(encoding="utf-8"), **kw)


def row(rel, key):
    return next(r for r in rel.rows if r["key"] == key)


# ---------------------------------------------------------------- auction results
def test_cg_result_single_security():
    r = run("cg_result", "63970")
    assert r.release_date == "2026-11-13" and len(r.rows) == 1
    x = row(r, "10Y")
    assert x["security"] == "6.94% GS 2036"
    assert x["notified_amount"] == 34000.0 and x["bids_received_amount"] == 73016.6
    assert x["accepted_amount"] == 33947.718 and x["cutoff_yield"] == 7.3203
    assert x["devolvement_amount"] == 0.0 and x["bid_cover"] == 2.15


def test_cg_result_two_securities():
    r = run("cg_result", "63937")
    assert {x["key"] for x in r.rows} == {"15Y", "50Y"}
    assert row(r, "50Y")["cutoff_yield"] == 7.7708


def test_cg_result_uses_announcement_maturity_when_given():
    # illustrative date: ~10.05 years after the 13 Nov 2026 auction
    r = run("cg_result", "63970", maturities={"6.94% GS 2036": "2036-12-01"})
    assert row(r, "10Y")["bucket_approx"] is False


def test_tbill_result_three_tenors():
    r = run("tbill_result", "63956")
    assert [x["key"] for x in r.rows] == ["91D", "182D", "364D"]
    x = row(r, "91D")
    assert x["notified_amount"] == 8000.0 and x["accepted_amount"] == 7600.0
    assert x["total_allotment_amount"] == 19200.0 and x["cutoff_yield"] == 5.8681 and x["bid_cover"] == 3.38


def test_sg_result_whole_auction_summary():
    r = run("sg_result", "63950")
    x = row(r, "ALL")
    assert (x["notified_amount"], x["bids_received_amount"], x["accepted_amount"], x["total_allotment_amount"]) == \
        (29050.0, 82868.2, 25921.784, 27083.882)


def test_omo_result_sale():
    r = run("omo_result", "63798")
    assert r.fields["direction"] == "sale" and r.fields["settlement_date"] == "2026-10-14"
    x = row(r, "sale")
    assert x["notified_amount"] == 25000.0 and x["accepted_amount"] == 25000.0 and x["bid_cover"] == 2.22


def test_vrr_and_vrrr_results():
    v = row(run("vrrr_result", "63968"), "3D")
    assert v["notified_amount"] == 75000.0 and v["accepted_amount"] == 38592.0
    assert v["cutoff_rate"] == 5.49 and v["bid_cover"] == 0.51
    w = row(run("vrr_result", "63945"), "4D")
    assert w["accepted_amount"] == 50003.0 and w["wtd_avg_rate"] == 5.54


# ---------------------------------------------------------------- announcements
def test_cg_announcement_buckets_from_maturity_dates():
    r = run("cg_announcement", "63983")
    assert r.fields["auction_date"] == "2026-11-20" and r.fields["total_notified_amount"] == 33000.0
    assert row(r, "5Y")["security"] == "6.53% GS 2031" and row(r, "39Y")["notified_amount"] == 14000.0


def test_tbill_and_sg_announcements():
    t = run("tbill_announcement", "63975")
    assert [x["notified_amount"] for x in t.rows] == [8000.0, 8000.0, 7000.0]
    s = run("sg_announcement", "63976")
    assert row(s, "ALL")["notified_amount"] == 23300.0 and len(s.fields["detail"]) == 22


def test_vrr_vrrr_announcements():
    assert row(run("vrrr_announcement", "63984"), "2D")["notified_amount"] == 50000.0
    assert row(run("vrr_announcement", "63943"), "4D")["reversal_date"] == "2026-11-13"


# ---------------------------------------------------------------- publications
def test_bop_values_and_year_ago():
    r = run("bop", "63974")
    f = r.fields
    assert f["period"] == "September 2026" and f["ytd_period"] == "April-September 2026"
    assert f["current_account_balance"] == -7.4 and f["trade_balance"] == -30.0 and f["fdi_net"] == -4.9
    assert f["ytd_current_account_balance"] == -25.8 and f["monetary_movements"] == -8.8
    assert "current_account_balance" in r.prior_year and "_prior_year" not in f


def test_wss_series():
    f = run("wss", "63972").fields
    assert f["forex_reserves_total_usd_mn"] == 719547.0 and f["forex_as_on"] == "2026-11-06"
    assert f["aggregate_deposits_yoy_pct"] == 16.9 and f["bank_credit_yoy_pct"] == 19.5 and f["m3_yoy_pct"] == 16.5


def test_mpc_hike_with_projections_and_votes():
    r = run("mpc_minutes", "63839")
    f = r.fields
    assert (f["decision"], f["repo_rate"], f["repo_change_bps"], f["stance"]) == ("hike", 5.5, 25, "calibrated tightening")
    assert (f["inflation_projection"], f["inflation_projection_period"]) == (5.2, "2026-27")
    assert (f["growth_projection"], f["growth_projection_period"]) == (7.1, "2026-27")
    assert f["unanimous"] is True and len(r.rows) == 6 and all(x["vote"] == "hike" for x in r.rows)


def test_mpc_without_full_year_projection_is_flagged_not_guessed():
    r = run("mpc_minutes", "62261")
    assert r.fields["decision"] == "hold" and r.fields["growth_projection"] is None
    assert r.fields["needs_review"]


def test_sectoral_credit_text_rows():
    r = run("sectoral_credit", "62135")
    got = {x["key"]: (x["yoy_growth_pct"], x["prior_year_yoy_growth_pct"]) for x in r.rows}
    assert got == {"Non-food credit": (14.4, 11.1), "Agriculture": (12.1, 12.5), "Industry": (13.3, 7.5),
                   "Services": (15.3, 11.5), "Personal loans": (14.4, 12.0)}
    assert "needs_review" not in r.fields


def test_every_fixture_extracts():
    cases = {"cg_announcement": ["63983", "63952"], "cg_result": ["63970", "63937"], "sg_announcement": ["63976", "63931"],
             "sg_result": ["63950"], "tbill_announcement": ["63975", "63942"], "tbill_result": ["63956"],
             "vrrr_announcement": ["63984", "63965"], "vrrr_result": ["63968", "63962"], "vrr_announcement": ["63943"],
             "vrr_result": ["63945"], "bop": ["63974"], "wss": ["63972", "63939"], "mpc_minutes": ["63839", "62261"],
             "sectoral_credit": ["62135", "62301"], "omo_result": ["63798"]}
    for item, prids in cases.items():
        for p in prids:
            assert run(item, p).fields is not None


def test_unknown_item_raises():
    with pytest.raises(ExtractionError):
        run("omo_announcement", "63983")