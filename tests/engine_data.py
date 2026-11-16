"""Synthetic fixture data for engine tests. Numbers are illustrative, NOT real RBI figures."""
from rbi_tracker.engine import Release


def rel(item_id, date, fields=None, rows=None, prior_year=None):
    return Release(item_id=item_id, release_date=date, reference=f"{item_id} {date}",
                   fields=fields or {}, rows=rows or [], prior_year=prior_year or {})


def find(diff, metric, key=None, comparison=None):
    """All changes in a diff matching metric (and optionally key / comparison)."""
    return [c for c in diff.changes if c.metric == metric
            and (key is None or c.key == key)
            and (comparison is None or c.comparison == comparison)]


# ---- CG auction ------------------------------------------------------------------------------
CG_ANN_PREV = rel("cg_announcement", "2026-11-06", rows=[
    {"key": "5Y", "security": "6.33% GS 2031", "notified_amount": 12000},
    {"key": "10Y", "security": "6.48% GS 2036", "notified_amount": 14000},
    {"key": "14Y", "security": "6.68% GS 2040", "notified_amount": 12000},
])
CG_ANN_NEW = rel("cg_announcement", "2026-11-13", rows=[
    {"key": "10Y", "security": "6.48% GS 2036", "notified_amount": 15000},
    {"key": "14Y", "security": "6.68% GS 2040", "notified_amount": 12000},
    {"key": "30Y", "security": "7.10% GS 2056", "notified_amount": 8000},
])

CG_RES_PREV = rel("cg_result", "2026-11-07", rows=[
    {"key": "10Y", "notified_amount": 14000, "accepted_amount": 14000, "cutoff_yield": 6.52, "bid_cover": 2.10},
    {"key": "14Y", "notified_amount": 12000, "accepted_amount": 12000, "cutoff_yield": 6.60, "bid_cover": 2.40},
])
CG_RES_NEW = rel("cg_result", "2026-11-14", rows=[
    {"key": "10Y", "notified_amount": 15000, "accepted_amount": 15000, "cutoff_yield": 6.56, "bid_cover": 2.31},
    {"key": "14Y", "notified_amount": 12000, "accepted_amount": 12000, "cutoff_yield": 6.60, "bid_cover": 2.40},
])

# ---- OMO -------------------------------------------------------------------------------------
OMO_ANN_PREV = rel("omo_announcement", "2026-10-20", fields={"direction": "purchase"},
                   rows=[{"key": "10Y", "notified_amount": 20000}])
OMO_ANN_NEW = rel("omo_announcement", "2026-11-10", fields={"direction": "sale"},
                  rows=[{"key": "10Y", "notified_amount": 20000}])
OMO_RES_PREV = rel("omo_result", "2026-10-22", fields={"direction": "purchase"},
                   rows=[{"key": "10Y", "notified_amount": 20000, "accepted_amount": 18000, "cutoff_price": 98.50}])
OMO_RES_NEW = rel("omo_result", "2026-11-12", fields={"direction": "purchase"},
                  rows=[{"key": "10Y", "notified_amount": 20000, "accepted_amount": 18000, "cutoff_price": 98.75}])

# ---- T-Bill / VRRR -----------------------------------------------------------------------------
TB_RES_PREV = rel("tbill_result", "2026-11-04", rows=[
    {"key": "91D", "notified_amount": 8000, "accepted_amount": 8000, "cutoff_yield": 5.90, "bid_cover": 3.0},
    {"key": "182D", "notified_amount": 6000, "accepted_amount": 6000, "cutoff_yield": 6.00, "bid_cover": 2.5},
])
TB_RES_NEW = rel("tbill_result", "2026-11-11", rows=[
    {"key": "91D", "notified_amount": 8000, "accepted_amount": 8000, "cutoff_yield": 5.88, "bid_cover": 3.2},
    {"key": "182D", "notified_amount": 6000, "accepted_amount": 6000, "cutoff_yield": 6.05, "bid_cover": 2.5},
])
VRRR_RES_PREV = rel("vrrr_result", "2026-11-03", rows=[
    {"key": "14D", "notified_amount": 100000, "accepted_amount": 60000, "cutoff_rate": 5.49, "bid_cover": 0.6}])
VRRR_RES_NEW = rel("vrrr_result", "2026-11-10", rows=[
    {"key": "14D", "notified_amount": 100000, "accepted_amount": 70000, "cutoff_rate": 5.50, "bid_cover": 0.7}])

# ---- WSS / Bulletin ----------------------------------------------------------------------------
WSS_PREV = rel("wss", "2026-11-06", fields={"reserve_money": 3400000, "forex_reserves": 650000, "bank_credit": 1800000})
WSS_NEW = rel("wss", "2026-11-13", fields={"reserve_money": 3434000, "forex_reserves": 650000, "bank_credit": 1809000,
                                          "aggregate_deposits": 2300000})
BUL_PREV = rel("bulletin", "2026-10-25", fields={"gdp_growth": 6.5, "articles": ["State of the Economy", "Fiscal Review"]})
BUL_NEW = rel("bulletin", "2026-11-25", fields={"gdp_growth": 6.7,
                                              "articles": ["State of the Economy", "  banking   sector outlook ", "Fiscal Review"]})

# ---- BoP ----------------------------------------------------------------------------------------
BOP_PREV = rel("bop", "2026-09-01", fields={"quarter": "Q1", "current_account_balance": -9.0, "trade_balance": -20.0,
                                           "capital_account_balance": 18.0})
BOP_NEW = rel("bop", "2026-12-01", fields={"quarter": "Q2", "current_account_balance": 13.5, "trade_balance": -22.0,
                                          "capital_account_balance": 20.0},
              prior_year={"current_account_balance": -8.7, "trade_balance": -21.0, "capital_account_balance": 20.0})

# ---- Sectoral credit -----------------------------------------------------------------------------
CREDIT_PREV = rel("sectoral_credit", "2026-10-31", rows=[
    {"key": "Agriculture", "outstanding": 2000000, "yoy_growth_pct": 10.0},
    {"key": "Industry", "outstanding": 4000000, "yoy_growth_pct": 8.0},
    {"key": "Services", "outstanding": 5000000, "yoy_growth_pct": 14.0},
])
CREDIT_NEW = rel("sectoral_credit", "2026-11-30", rows=[
    {"key": "Agriculture", "outstanding": 2010000, "yoy_growth_pct": 9.2},
    {"key": "Industry", "outstanding": 4000000, "yoy_growth_pct": 8.0},
    {"key": "Services", "outstanding": 5100000, "yoy_growth_pct": 15.1},
    {"key": "Personal Loans", "outstanding": 6000000, "yoy_growth_pct": 12.0},
])

# ---- MPC minutes ----------------------------------------------------------------------------------
_MEMBERS = ["Member A", "Member B", "Member C", "Member D", "Member E", "Member F"]
MPC_PREV = rel("mpc_minutes", "2026-10-22",
               fields={"repo_rate": 5.50, "decision": "hold", "stance": "neutral", "inflation_projection": 3.1,
                       "growth_projection": 6.5, "inflation_outlook": "Inflation to remain benign",
                       "growth_outlook": "Growth resilient"},
               rows=[{"key": m, "vote": "hold", "vote_bps": 0, "rationale": "r"} for m in _MEMBERS])
MPC_NEW = rel("mpc_minutes", "2026-12-19",
              fields={"repo_rate": 5.25, "decision": "cut", "stance": "neutral", "inflation_projection": 3.0,
                      "growth_projection": 6.5, "inflation_outlook": "Inflation to stay soft",
                      "growth_outlook": "Growth resilient"},
              rows=[{"key": m, "vote": "cut" if m in ("Member A", "Member F") else "hold",
                     "vote_bps": 25 if m in ("Member A", "Member F") else 0, "rationale": "r"} for m in _MEMBERS])
