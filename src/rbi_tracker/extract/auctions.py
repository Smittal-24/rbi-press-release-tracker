"""Extractors for CG / SG / T-Bill / OMO / VRR / VRRR releases (brief section 5).

Each function takes (soup, ctx) and returns (fields, rows). ctx = {"release_date": ISO date,
"maturities": {security name: ISO maturity date}} where `maturities` is built from earlier
announcements (it lets a CG result page, which names bonds by year only, get an exact tenor bucket).

Definitions (confirmed): amount accepted = competitive bids accepted; bid-cover = competitive bids
(or offers) received / notified amount, which RBI does not publish, so it is marked as derived.
`total_allotment_amount` = competitive + non-competitive accepted (published for SG, summed for CG/T-Bill).
"""
from __future__ import annotations

import re
from datetime import date

from .common import (ExtractionError, body_node, body_text, clean, first_number, grid, leaf_tables, metric,
                     note_number, num, parse_date, read_columns)
from .tenor import tenor_bucket, unique_keys


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _ratio(a: float | None, b: float | None) -> float | None:
    return round(a / b, 2) if a is not None and b not in (None, 0) else None


def _days_key(text: str) -> str:
    m = re.search(r"(\d+)\s*-?\s*day", text, re.I)
    if m:
        return f"{int(m.group(1))}D"
    if re.search(r"overnight", text, re.I):
        return "1D"
    raise ExtractionError(f"cannot read a tenor in days from {text!r}")


def _header_index(rows: list[list[str]], *words: str) -> int:
    for i, r in enumerate(rows):
        joined = " ".join(r).lower()
        if all(w in joined for w in words):
            return i
    raise ExtractionError(f"table header with {words} not found")


# ----------------------------------------------------------------------------- announcements
def cg_announcement(soup, ctx):
    rows_g = grid(leaf_tables(body_node(soup))[0])
    hi = _header_index(rows_g, "security", "notified")
    auction = settle = None
    items = []
    for r in rows_g[hi + 1:]:
        if not r[0].isdigit():
            continue
        items.append({"security": r[1], "maturity": parse_date(r[2]), "notified": num(r[3])})
        if auction is None and len(r) >= 7:
            auction, settle = parse_date(r[5]), parse_date(r[6])
    if not items:
        raise ExtractionError("no securities found in CG announcement")
    ref = auction or date.fromisoformat(ctx["release_date"])
    keys, approx = [], []
    for it in items:
        k, a = tenor_bucket(it["security"], ref, it["maturity"])
        keys.append(k)
        approx.append(a)
    rows = [{"key": k, "security": it["security"], "maturity_date": _iso(it["maturity"]),
             "notified_amount": it["notified"], "bucket_approx": a}
            for k, it, a in zip(unique_keys(keys), items, approx)]
    fields = {"auction_date": _iso(auction), "settlement_date": _iso(settle),
              "total_notified_amount": sum(i["notified"] or 0 for i in items)}
    return fields, rows


def tbill_announcement(soup, ctx):
    rows_g = grid(leaf_tables(body_node(soup))[0])
    hi = _header_index(rows_g, "treasury bill", "notified")
    auction = settle = None
    rows = []
    for r in rows_g[hi + 1:]:
        if not r[0].strip(".").isdigit():
            continue
        rows.append({"key": _days_key(r[1]), "security": r[1], "notified_amount": num(r[2])})
        if auction is None and len(r) >= 5:
            auction, settle = parse_date(r[3]), parse_date(r[4])
    if not rows:
        raise ExtractionError("no tenors found in T-Bill announcement")
    fields = {"auction_date": _iso(auction), "settlement_date": _iso(settle),
              "total_notified_amount": sum(r["notified_amount"] or 0 for r in rows)}
    return fields, rows


def sg_announcement(soup, ctx):
    """Whole-auction total only (confirmed). Per-state offers are kept in fields['detail']."""
    rows_g = grid(leaf_tables(body_node(soup))[0])
    hi = _header_index(rows_g, "state", "amount")
    state, detail = "", []
    for r in rows_g[hi + 1:]:
        if len(r) >= 5 and r[0].rstrip(".").isdigit():
            state, amount, tenor, kind = r[1], num(r[2]), r[3], r[4]
        elif len(r) == 3:
            amount, tenor, kind = num(r[0]), r[1], r[2]
        else:
            continue
        detail.append({"state": state, "amount": amount, "tenor": tenor, "type": kind})
    m = re.search(r"aggregate amount of\s*\u20b9?\s*([\d,]+)", body_text(soup))
    stated = float(m.group(1).replace(",", "")) if m else None
    summed = sum(d["amount"] or 0 for d in detail)
    total = stated if stated is not None else summed
    fields = {"total_notified_amount": total, "detail": detail}
    if stated is not None and abs(stated - summed) > 0.5:
        fields["needs_review"] = [f"state amounts add up to {summed:g} but the page states {stated:g}"]
    return fields, [{"key": "ALL", "security": "All State Government securities", "notified_amount": total}]


def vrr_announcement(soup, ctx):
    rows_g = grid(leaf_tables(body_node(soup))[0])
    hi = _header_index(rows_g, "notified", "tenor")
    rows = []
    for r in rows_g[hi + 1:]:
        if not r[0].isdigit():
            continue
        rows.append({"key": f"{int(num(r[2]))}D", "notified_amount": num(r[1]), "window": r[3],
                     "reversal_date": _iso(parse_date(r[4]))})
    if not rows:
        raise ExtractionError("no tenor found in VRR/VRRR announcement")
    m = re.search(r"auction on (?:[A-Za-z]+, )?([A-Za-z]+ \d{1,2}, \d{4})", body_text(soup))
    return {"operation_date": _iso(parse_date(m.group(1))) if m else None}, rows


# ----------------------------------------------------------------------------- results
def _column_row(m, i):
    """Numbers for one security / tenor column of a CG or T-Bill result table."""
    comp_recv = num(metric(m, r"^competitive bids received/amount", i))
    comp_acc = num(metric(m, r"^competitive bids accepted/amount", i))
    nc_recv = num(metric(m, r"^non-competitive bids received/amount", i))
    nc_acc = num(metric(m, r"^non-competitive bids accepted/amount", i))
    notified = num(metric(m, r"^notified amount", i))
    row = {
        "notified_amount": notified,
        "bids_received_number": num(metric(m, r"^competitive bids received/number", i)),
        "bids_received_amount": comp_recv,
        "accepted_number": num(metric(m, r"^competitive bids accepted/number", i)),
        "accepted_amount": comp_acc,
        "noncomp_received_amount": nc_recv,
        "noncomp_accepted_amount": nc_acc,
        "total_allotment_amount": round(comp_acc + nc_acc, 3) if comp_acc is not None and nc_acc is not None else None,
        "cutoff_price": num(metric(m, r"^cut-?off price", i)),
        "cutoff_yield": note_number(metric(m, r"^cut-?off price", i, note=True), "YTM"),
        "wtd_avg_price": num(metric(m, r"^weighted average price", i)),
        "wtd_avg_yield": note_number(metric(m, r"^weighted average price", i, note=True), "WAY"),
        "devolvement_amount": num(metric(m, r"^devolvement", i)),
        "bid_cover": _ratio(comp_recv, notified),
        "derived": ["bid_cover", "total_allotment_amount"],
    }
    return row


def cg_result(soup, ctx):
    cols, m = read_columns(leaf_tables(body_node(soup)))
    ref = date.fromisoformat(ctx["release_date"])
    maturities = ctx.get("maturities", {})
    keys, approx = [], []
    for c in cols:
        mat = maturities.get(c)
        k, a = tenor_bucket(c, ref, date.fromisoformat(mat) if mat else None)
        keys.append(k)
        approx.append(a)
    rows = []
    for i, (k, c, a) in enumerate(zip(unique_keys(keys), cols, approx)):
        rows.append({"key": k, "security": c, "bucket_approx": a, **_column_row(m, i)})
    return {}, rows


def tbill_result(soup, ctx):
    cols, m = read_columns(leaf_tables(body_node(soup)))
    rows = [{"key": _days_key(c), "security": c, **_column_row(m, i)} for i, c in enumerate(cols)]
    return {}, rows


def sg_result(soup, ctx):
    """Whole-auction summary (confirmed): RBI's published Total column; cut-off yield is derived as the
    average of the states' cut-off yields weighted by competitive amount accepted."""
    cols, m = read_columns(leaf_tables(body_node(soup)))
    t = cols.index("Total") if "Total" in cols else None
    states = [i for i, c in enumerate(cols) if c != "Total"]
    detail = []
    for i in states:
        detail.append({
            "security": cols[i],
            "notified_amount": num(metric(m, r"^notified amount", i)),
            "bids_received_amount": num(metric(m, r"^competitive bids received/amount", i)),
            "accepted_amount": num(metric(m, r"^competitive bids accepted/amount", i)),
            "cutoff_yield": num(metric(m, r"^cut-?off yield", i)),
            "wtd_avg_yield": num(metric(m, r"^weighted average yield", i)),
            "total_allotment_amount": num(metric(m, r"^total allotment amount", i)),
        })

    def total(pattern, field):
        if t is not None:
            v = num(metric(m, pattern, t))
            if v is not None:
                return v
        vals = [d[field] for d in detail if d[field] is not None]
        return round(sum(vals), 3) if vals else None

    notified = total(r"^notified amount", "notified_amount")
    recv = total(r"^competitive bids received/amount", "bids_received_amount")
    acc = total(r"^competitive bids accepted/amount", "accepted_amount")
    allot = total(r"^total allotment amount", "total_allotment_amount")
    pairs = [(d["accepted_amount"], d["cutoff_yield"]) for d in detail
             if d["accepted_amount"] and d["cutoff_yield"] is not None]
    cutoff = round(sum(a * y for a, y in pairs) / sum(a for a, _ in pairs), 4) if pairs else None
    row = {"key": "ALL", "security": "All State Government securities", "notified_amount": notified,
           "bids_received_amount": recv, "accepted_amount": acc, "total_allotment_amount": allot,
           "cutoff_yield": cutoff, "bid_cover": _ratio(recv, notified),
           "derived": ["cutoff_yield", "bid_cover"]}
    return {"detail": detail}, [row]


def vrr_result(soup, ctx):
    cols, m = read_columns(leaf_tables(body_node(soup)))
    rows = []
    for i, c in enumerate(cols):
        notified = num(metric(m, r"^notified amount", i))
        recv = num(metric(m, r"^total amount of (offers|bids) received", i))
        rows.append({
            "key": _days_key(c), "notified_amount": notified, "bids_received_amount": recv,
            "accepted_amount": num(metric(m, r"^amount (accepted|allotted)", i)),
            "cutoff_rate": num(metric(m, r"^cut ?off rate", i)),
            "wtd_avg_rate": num(metric(m, r"^weighted average rate", i)),
            "bid_cover": _ratio(recv, notified), "derived": ["bid_cover"],
        })
    return {}, rows


def omo_result(soup, ctx):
    """Whole-operation summary (confirmed). Key is the direction ('sale' / 'purchase') so sale and
    purchase results are never compared with each other. Cut-off yield is derived (accepted-weighted)."""
    text = clean(soup.get_text(" ", strip=True))
    d = re.search(r"OMO\s+(Sale|Purchase)", text, re.I)
    if not d:
        raise ExtractionError("cannot tell whether this OMO result is a sale or a purchase")
    direction = d.group(1).lower()
    body = body_node(soup)
    summary = {}
    for table in leaf_tables(body):
        for r in grid(table):
            if len(r) == 2 and ":" in r[1]:
                summary[r[0].lower()] = first_number(r[1])
    notified = next((v for k, v in summary.items() if "notified" in k), None)
    bid = next((v for k, v in summary.items() if "amount bid" in k), None)
    accepted = next((v for k, v in summary.items() if "amount accepted" in k), None)
    cols, m = read_columns(leaf_tables(body))
    detail = []
    for i, c in enumerate(cols):
        detail.append({
            "security": c,
            "bids_received_amount": num(metric(m, r"^total bid amount \(face value\) \(", i)),
            "accepted_amount": num(metric(m, r"accepted by rbi", i)),
            "cutoff_yield": num(metric(m, r"^cut ?off yield", i)),
            "cutoff_price": num(metric(m, r"^cut ?off price", i)),
            "wtd_avg_yield": num(metric(m, r"^weighted average yield", i)),
        })
    pairs = [(x["accepted_amount"], x["cutoff_yield"]) for x in detail
             if x["accepted_amount"] and x["cutoff_yield"] is not None]
    cutoff = round(sum(a * y for a, y in pairs) / sum(a for a, _ in pairs), 4) if pairs else None
    held = re.search(r"held on ([A-Za-z]+ \d{1,2}, \d{4})", text)
    settle = re.search(r"Settlement on ([A-Za-z]+ \d{1,2}, \d{4})", text)
    row = {"key": direction, "security": f"OMO {direction}", "notified_amount": notified,
           "bids_received_amount": bid, "accepted_amount": accepted, "cutoff_yield": cutoff,
           "bid_cover": _ratio(bid, notified), "derived": ["cutoff_yield", "bid_cover"]}
    fields = {"direction": direction, "operation_date": _iso(parse_date(held.group(1))) if held else None,
              "settlement_date": _iso(parse_date(settle.group(1))) if settle else None, "detail": detail}
    return fields, [row]