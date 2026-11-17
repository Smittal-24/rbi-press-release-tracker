"""Message wording for T-Bills (table), Balance of Payments and Sectoral credit (analysis), on real pages."""
from pathlib import Path

from rbi_tracker.engine import compare
from rbi_tracker.extract.extract import extract
from rbi_tracker.notify.gchat import format_release

FIX = Path(__file__).parent / "fixtures" / "rbi"


def L(item, prid):
    return extract(item, (FIX / f"{prid}.html").read_text(encoding="utf-8"))


def msg(label, rel, prev=None):
    return format_release(label, rel, compare(rel, prev), "URL", prev)


def test_tbill_table_first_result_has_na_yield_change():
    m = msg("T-Bill Auction - Result", L("tbill_result", "63956"))
    assert "```" in m and "91-Day" in m and "364-Day" in m
    assert "Cut-off yield (%)" in m and "5.8681" in m and "6.6394" in m
    assert "Non-comp. accepted" in m and "11,600" in m
    assert "Yield chg vs prev (bps)" in m and "n/a" in m
    assert "above notified" not in m and "accepted vs notified" not in m


def test_tbill_table_shows_yield_change_in_bps_per_tenor():
    new = L("tbill_result", "63956")
    prev = L("tbill_result", "63956")
    prev.release_date = "2026-11-04"
    for r in prev.rows:
        r["cutoff_yield"] = round(r["cutoff_yield"] - 0.05, 4)      # previous auction was 5 bps lower
    m = msg("T-Bill Auction - Result", new, prev)
    line = next(ln for ln in m.splitlines() if ln.startswith("Yield chg vs prev"))
    assert line.count("+5.0") == 3
    assert "previous T-Bill auction (4 Nov 2026)" in m


def test_bop_message_is_analysis_not_a_list_of_lines():
    m = msg("Balance of Payments", L("bop", "63974"))
    assert "```" not in m and "PRIORITY:" not in m and "\n- " not in m
    assert "Current account:" in m and "deficit of US$7.4bn, wider than the US$5.2bn a year ago" in m
    assert "merchandise exports US$45.3bn (+24.5% y/y)" in m
    assert "Capital account:" in m and "swung from a deficit of US$0.4bn a year ago to a surplus of US$16.2bn" in m
    assert "Reserves rose by US$8.8bn" in m
    assert "Year to date (April-September 2026)" in m
    assert "Sign swings (priority)" in m and "overall balance vs year ago: deficit to surplus" in m


def test_credit_message_is_analysis_with_previous_release():
    a, b = L("sectoral_credit", "62135"), L("sectoral_credit", "62301")
    first, second = sorted([a, b], key=lambda r: r.release_date)
    m = msg("Sectoral Deployment of Bank Credit", second, first)
    assert "```" not in m and "y-o-y credit growth:" not in m
    assert "Non-food bank credit grew" in m and "against" in m
    assert "accelerating: Personal loans (+0.5pp), Services (+0.2pp)" in m
    assert "decelerating: Industry (-1.2pp), Agriculture (-0.7pp)" in m
    assert "Fastest-growing segment: Services" in m


def test_credit_message_first_release_has_no_comparison_text():
    m = msg("Sectoral Deployment of Bank Credit", L("sectoral_credit", "62135"))
    assert "Versus the previous release" not in m and "Non-food bank credit grew 14.4% y/y" in m