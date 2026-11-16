"""WSS, RBI Bulletin, Balance of Payments and Sectoral Deployment of Bank Credit (brief section 6)."""
from __future__ import annotations

from .models import Change, Diff, Release
from .utils import add_change, index_rows, pretty, record, to_num


def _compare_series(d: Diff, new: Release, prev: Release) -> None:
    """Every numeric field present in both releases: level and % change vs the prior release."""
    for name, val in new.fields.items():
        nv = to_num(val)
        if nv is None:
            continue
        if name not in prev.fields:
            d.info.append(f"New series in this release: {pretty(name)}")
            continue
        record(d, name, pretty(name), prev.fields[name], val, "level")
    for name, val in prev.fields.items():
        if to_num(val) is not None and to_num(new.fields.get(name)) is None and name not in new.fields:
            d.info.append(f"Series not present in this release: {pretty(name)}")


def compare_wss(new: Release, prev: Release | None) -> Diff:
    d = Diff(new.item_id, new.release_date, prev.release_date if prev else None)
    if prev is None:
        d.info.append("First recorded Weekly Statistical Supplement; nothing to compare against.")
        return d
    _compare_series(d, new, prev)
    return d


def _norm_title(t: str) -> str:
    return " ".join(str(t).split()).casefold()


def compare_bulletin(new: Release, prev: Release | None) -> Diff:
    d = Diff(new.item_id, new.release_date, prev.release_date if prev else None)
    if prev is None:
        d.info.append("First recorded RBI Bulletin; nothing to compare against.")
        d.new_articles = [str(t) for t in new.fields.get("articles", [])]
        return d
    _compare_series(d, new, prev)
    seen = {_norm_title(t) for t in prev.fields.get("articles", [])}
    d.new_articles = [str(t) for t in new.fields.get("articles", []) if _norm_title(t) not in seen]
    return d


def _sign_swing(c: Change, label_for_balance: bool) -> None:
    """Mark a Change as a priority sign swing if the value crossed zero."""
    p, n = c.previous, c.new
    if p is None or n is None or p * n >= 0:
        return
    word = ("surplus to deficit" if p > 0 else "deficit to surplus") if label_for_balance else (
        "positive to negative" if p > 0 else "negative to positive")
    c.priority = True
    c.note += f" [SIGN SWING: {word}]"


def compare_bop(new: Release, prev: Release | None) -> Diff:
    """Each figure vs the prior period AND vs the same period a year ago (prior_year, republished
    in the release itself). Any sign swing is a priority item."""
    d = Diff(new.item_id, new.release_date, prev.release_date if prev else None)
    if prev is None:
        d.info.append("First recorded Balance of Payments release; no prior period to compare against.")
    for name, val in new.fields.items():
        if to_num(val) is None:
            continue
        balance_like = "balance" in name or "invisibles" in name
        if prev is not None:
            c = record(d, name, f"{pretty(name)} vs prior period", prev.fields.get(name), val, "level")
            if c:
                _sign_swing(c, balance_like)
        if name in new.prior_year:
            c = record(d, name, f"{pretty(name)} vs year ago", new.prior_year.get(name), val, "level",
                       comparison="year_ago")
            if c:
                _sign_swing(c, balance_like)
    return d


def compare_credit(new: Release, prev: Release | None) -> Diff:
    """Per sector: change in y-o-y growth % (accelerating / decelerating), then outstanding level."""
    d = Diff(new.item_id, new.release_date, prev.release_date if prev else None)
    if prev is None:
        d.info.append("First recorded Sectoral Deployment of Bank Credit release; nothing to compare against.")
        return d
    new_rows = index_rows(new.rows, "sectoral_credit (new)")
    old_rows = index_rows(prev.rows, "sectoral_credit (previous)")
    for key, row in new_rows.items():
        if key not in old_rows:
            d.info.append(f"{key}: new sector/segment in this release (no prior)")
            continue
        o = old_rows[key]
        c = record(d, "yoy_growth_pct", f"{key} y-o-y credit growth", o.get("yoy_growth_pct"),
                   row.get("yoy_growth_pct"), "pp", key=key)
        if c:
            c.note += " - accelerating" if c.delta > 0 else " - decelerating"
        record(d, "outstanding", f"{key} outstanding credit", o.get("outstanding"), row.get("outstanding"),
               "amount", key=key)
    for key in old_rows:
        if key not in new_rows:
            d.info.append(f"{key}: reported last time but not in this release")
    return d
