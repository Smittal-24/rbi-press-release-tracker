"""Plain-language analysis for Balance of Payments and Sectoral Deployment of Bank Credit.

Rule-written (fixed wording from the numbers): predictable, free, no external service.
Every sentence is built only from figures in the release itself or the previous stored release.
"""
from __future__ import annotations

import re

from ..engine.models import Diff, Release
from ..engine.utils import pretty, to_num


# ----------------------------------------------------------------------------- helpers
def _g(d: dict, key: str):
    return to_num(d.get(key))


def _bn(x: float) -> str:
    return f"US${abs(x):,.1f}bn"


def _balance(x: float) -> str:
    if x > 0:
        return f"surplus of {_bn(x)}"
    if x < 0:
        return f"deficit of {_bn(x)}"
    return "a zero balance"


def _balance_move(cur: float | None, ago: float | None) -> str | None:
    """'deficit of US$7.4bn, wider than US$5.2bn a year ago' / 'swung from a deficit ... to a surplus ...'."""
    if cur is None:
        return None
    if ago is None:
        return _balance(cur)
    if cur * ago < 0:
        return f"swung from a {_balance(ago)} a year ago to a {_balance(cur)}"
    if cur == ago:
        return f"{_balance(cur)}, unchanged from a year ago"
    if cur < 0:
        adj = "wider" if abs(cur) > abs(ago) else "narrower"
    else:
        adj = "larger" if abs(cur) > abs(ago) else "smaller"
    return f"{_balance(cur)}, {adj} than the {_bn(ago)} a year ago"


def _flow(cur: float | None, ago: float | None) -> str | None:
    if cur is None:
        return None
    if ago in (None, 0):
        return _bn(cur)
    return f"{_bn(cur)} ({(cur - ago) / abs(ago) * 100:+.1f}% y/y)"


def _signed_bn(cur: float | None, ago: float | None) -> str | None:
    if cur is None:
        return None
    s = f"{cur:+.1f}bn"
    return s + (f" (year ago {ago:+.1f}bn)" if ago is not None else "")


def _join(parts: list[str | None], sep: str = "; ") -> str:
    return sep.join(p for p in parts if p)


# ----------------------------------------------------------------------------- Balance of Payments
def bop_summary(release: Release, previous: Release | None, diff: Diff) -> list[str]:
    f, py = release.fields, release.prior_year
    c = lambda k: _g(f, k)            # this period
    y = lambda k: _g(py, k)           # same period a year ago
    cy = lambda k: _g(f, "ytd_" + k)  # year to date
    yy = lambda k: _g(py, "ytd_" + k)
    lines = [f"Period: {f.get('period')}; year to date: {f.get('ytd_period')}. All figures US$ billion."]

    ca = _balance_move(c("current_account_balance"), y("current_account_balance"))
    if ca:
        detail = _join([
            ("trade " + _balance_move(c("trade_balance"), y("trade_balance"))) if c("trade_balance") is not None else None,
            ("merchandise exports " + _flow(c("merchandise_exports"), y("merchandise_exports")))
            if c("merchandise_exports") is not None else None,
            ("imports " + _flow(c("merchandise_imports"), y("merchandise_imports")))
            if c("merchandise_imports") is not None else None,
            ("net services " + _balance_move(c("net_services"), y("net_services")))
            if c("net_services") is not None else None,
            ("net transfers " + _signed_bn(c("net_transfers"), y("net_transfers")))
            if c("net_transfers") is not None else None,
            ("net income " + _signed_bn(c("net_income"), y("net_income")))
            if c("net_income") is not None else None,
        ])
        lines.append(f"*Current account:* {ca}; {detail}.")

    cap = _balance_move(c("capital_account_balance"), y("capital_account_balance"))
    if cap:
        parts = [(lab + " " + _signed_bn(c(k), y(k))) if c(k) is not None else None for lab, k in (
            ("FDI net", "fdi_net"), ("FPI net", "fpi_net"), ("ECB net", "ecb_net"),
            ("short-term credit", "short_term_credit_net"), ("banking capital", "banking_capital_net"),
            ("of which NRI deposits", "nri_deposits_net"), ("other capital", "other_capital_net"))]
        lines.append(f"*Capital account:* {cap}. Components: {_join(parts)}.")

    ob = _balance_move(c("overall_balance"), y("overall_balance"))
    if ob:
        mm = c("monetary_movements")
        res = ""
        if mm is not None:
            res = f" Reserves {'rose' if mm < 0 else 'fell'} by {_bn(mm)} (monetary movements {mm:+.1f}bn; the published minus sign means an increase in reserves)."
        lines.append(f"*Overall balance:* {ob}.{res}")

    ytd = _join([
        ("current account " + _balance_move(cy("current_account_balance"), yy("current_account_balance")))
        if cy("current_account_balance") is not None else None,
        ("trade " + _balance_move(cy("trade_balance"), yy("trade_balance"))) if cy("trade_balance") is not None else None,
        ("capital account " + _balance_move(cy("capital_account_balance"), yy("capital_account_balance")))
        if cy("capital_account_balance") is not None else None,
        ("overall balance " + _balance_move(cy("overall_balance"), yy("overall_balance")))
        if cy("overall_balance") is not None else None,
    ])
    if ytd:
        lines.append(f"*Year to date ({f.get('ytd_period')}):* {ytd}.")

    if previous is not None:
        pf = previous.fields
        moves = []
        for lab, k in (("current account", "current_account_balance"), ("trade balance", "trade_balance"),
                       ("overall balance", "overall_balance")):
            now, then = _g(f, k), _g(pf, k)
            if now is not None and then is not None:
                moves.append(f"{lab} {then:+.1f}bn -> {now:+.1f}bn")
        if moves:
            lines.append(f"*Versus the previous release ({pf.get('period')}):* {_join(moves)}.")

    swings = []
    for ch in diff.priority_changes:
        m = re.search(r"SIGN SWING: ([^\]]+)", ch.note)
        if m:
            swings.append(f"{pretty(ch.metric)} {'vs year ago' if ch.comparison == 'year_ago' else 'vs prior release'}: {m.group(1)}")
    if swings:
        lines.append("*Sign swings (priority):* " + _join(swings) + ".")
    return lines


# ----------------------------------------------------------------------------- Sectoral credit
def _pp(x: float) -> str:
    return f"{x:+.1f}pp"


def credit_summary(release: Release, previous: Release | None) -> list[str]:
    rows = {r["key"]: r for r in release.rows}
    month = release.fields.get("month") or ""
    lines: list[str] = []
    nfc = rows.get("Non-food credit")
    if nfc and to_num(nfc.get("yoy_growth_pct")) is not None:
        now, ago = to_num(nfc["yoy_growth_pct"]), to_num(nfc.get("prior_year_yoy_growth_pct"))
        s = f"Non-food bank credit grew {now:.1f}% y/y in {month}"
        if ago is not None:
            s += f", against {ago:.1f}% a year earlier ({_pp(now - ago)})"
        if previous is not None:
            prow = next((r for r in previous.rows if r["key"] == "Non-food credit"), None)
            if prow and to_num(prow.get("yoy_growth_pct")) is not None:
                d = now - to_num(prow["yoy_growth_pct"])
                s += (f"; unchanged from the previous release ({previous.fields.get('month')})" if abs(d) < 0.05
                      else f"; {_pp(d)} versus the previous release ({previous.fields.get('month')})")
        lines.append(s + ".")

    sectors = [r for r in release.rows if r["key"] != "Non-food credit" and to_num(r.get("yoy_growth_pct")) is not None]
    if previous is not None:
        prev = {r["key"]: to_num(r.get("yoy_growth_pct")) for r in previous.rows}
        up, down, flat = [], [], []
        for r in sectors:
            if prev.get(r["key"]) is None:
                continue
            d = to_num(r["yoy_growth_pct"]) - prev[r["key"]]
            (up if d > 0.05 else down if d < -0.05 else flat).append((r["key"], d))
        bits = []
        if up:
            bits.append("accelerating: " + ", ".join(f"{k} ({_pp(d)})" for k, d in sorted(up, key=lambda x: -x[1])))
        if down:
            bits.append("decelerating: " + ", ".join(f"{k} ({_pp(d)})" for k, d in sorted(down, key=lambda x: x[1])))
        if flat:
            bits.append("unchanged: " + ", ".join(k for k, _ in flat))
        if bits:
            lines.append("Versus the previous release, " + "; ".join(bits) + ".")

    yoy = [(r["key"], to_num(r["yoy_growth_pct"]) - to_num(r["prior_year_yoy_growth_pct"])) for r in sectors
           if to_num(r.get("prior_year_yoy_growth_pct")) is not None]
    if yoy:
        hi, lo = max(yoy, key=lambda x: x[1]), min(yoy, key=lambda x: x[1])
        s = f"Versus a year ago, the biggest pick-up in growth is in {hi[0]} ({_pp(hi[1])})"
        if lo[1] < 0:
            s += f" and the biggest slowdown is in {lo[0]} ({_pp(lo[1])})"
        lines.append(s + ".")
    if sectors:
        fast = max(sectors, key=lambda r: to_num(r["yoy_growth_pct"]))
        slow = min(sectors, key=lambda r: to_num(r["yoy_growth_pct"]))
        lines.append(f"Fastest-growing segment: {fast['key']} at {to_num(fast['yoy_growth_pct']):.1f}% y/y; "
                     f"slowest: {slow['key']} at {to_num(slow['yoy_growth_pct']):.1f}% y/y.")
    return lines