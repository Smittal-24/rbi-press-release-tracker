from rbi_tracker.engine import compare
from engine_data import *  # noqa: F401,F403


# ---------------- WSS ----------------
def test_wss_level_and_pct_change():
    d = compare(WSS_NEW, WSS_PREV)
    c = find(d, "reserve_money")[0]
    assert (c.previous, c.new, c.delta, c.pct_change) == (3400000, 3434000, 34000, 1.0)
    assert "forex reserves" in d.unchanged
    assert any("aggregate deposits" in line for line in d.info)   # new series noted, not diffed


# ---------------- Bulletin ----------------
def test_bulletin_new_articles_and_data_change():
    d = compare(BUL_NEW, BUL_PREV)
    assert d.new_articles == ["  banking   sector outlook "]       # only the genuinely new title
    assert find(d, "gdp_growth")[0].delta == 0.2
    assert not find(d, "articles")                                  # no 'change' concept for articles


def test_bulletin_title_match_ignores_case_and_spacing():
    prev = rel("bulletin", "2026-10-25", fields={"articles": ["Banking Sector Outlook"]})
    new = rel("bulletin", "2026-11-25", fields={"articles": ["banking  sector   OUTLOOK", "New Piece"]})
    assert compare(new, prev).new_articles == ["New Piece"]


# ---------------- BoP ----------------
def test_bop_sequential_and_yoy_with_sign_swing():
    d = compare(BOP_NEW, BOP_PREV)
    seq = find(d, "current_account_balance", comparison="previous")[0]
    yoy = find(d, "current_account_balance", comparison="year_ago")[0]
    assert (seq.previous, seq.new, seq.delta) == (-9.0, 13.5, 22.5)
    assert seq.pct_change == 250.0                                  # abs(prev) denominator
    assert seq.priority and "deficit to surplus" in seq.note
    assert yoy.priority and yoy.previous == -8.7


def test_bop_no_swing_is_not_priority():
    d = compare(BOP_NEW, BOP_PREV)
    trade = find(d, "trade_balance", comparison="previous")[0]
    assert trade.delta == -2.0 and not trade.priority
    assert "capital account balance vs year ago" in d.unchanged


def test_bop_first_release_still_gives_yoy():
    d = compare(BOP_NEW, None)
    assert not d.has_previous
    assert find(d, "current_account_balance", comparison="year_ago")
    assert not find(d, "current_account_balance", comparison="previous")


# ---------------- Sectoral credit ----------------
def test_credit_growth_accelerating_and_decelerating():
    d = compare(CREDIT_NEW, CREDIT_PREV)
    agri = find(d, "yoy_growth_pct", "Agriculture")[0]
    svc = find(d, "yoy_growth_pct", "Services")[0]
    assert agri.delta == -0.8 and agri.unit == "pp" and "decelerating" in agri.note
    assert svc.delta == 1.1 and "accelerating" in svc.note
    assert not find(d, "yoy_growth_pct", "Industry")
    assert "Industry y-o-y credit growth" in d.unchanged
    assert any("Personal Loans" in line for line in d.info)         # new sector noted
