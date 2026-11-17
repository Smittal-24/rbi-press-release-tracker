"""Announcement and result comparison for CG / SG / T-Bill / OMO / VRR / VRRR (brief section 6).

Rows are matched by their "key" (the tenor bucket chosen by the extractor, e.g. "10Y", "91D", "14D"),
so a result is only ever compared with the previous result of the SAME item type and SAME tenor.
"""
from __future__ import annotations

from .models import Diff, Release
from .utils import add_change, fmt, index_rows, pct_change, record, signed, to_num, EPS

FAMILY_LABEL = {"cg": "CG", "sg": "SG", "tbill": "T-Bill", "omo": "OMO", "vrr": "VRR", "vrrr": "VRRR"}
AUCTION_FAMILIES = tuple(FAMILY_LABEL)

# (row field, display name, kind) - cut-off is a yield/rate for most, a price for some OMOs
CUTOFF_FIELDS = (
    ("cutoff_yield", "cut-off yield", "yield"),
    ("cutoff_rate", "cut-off rate", "yield"),
    ("cutoff_price", "cut-off price", "price"),
)


def split_item_id(item_id: str) -> tuple[str, str]:
    family, _, kind = item_id.rpartition("_")
    return family, kind


def _total(rows: dict[str, dict], field: str) -> float | None:
    vals = [to_num(r.get(field)) for r in rows.values()]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def compare_announcement(new: Release, prev: Release | None) -> Diff:
    family, _ = split_item_id(new.item_id)
    lab = FAMILY_LABEL[family]
    d = Diff(new.item_id, new.release_date, prev.release_date if prev else None)
    if prev is None:
        d.info.append(f"First recorded {lab} announcement; nothing to compare against.")
        return d

    new_rows = index_rows(new.rows, f"{new.item_id} (new)")
    old_rows = index_rows(prev.rows, f"{prev.item_id} (previous)")

    # OMO direction flip (purchase <-> sale)
    nd, od = new.fields.get("direction"), prev.fields.get("direction")
    if nd and od:
        if str(nd).strip().lower() != str(od).strip().lower():
            add_change(d, "direction", f"{lab} direction flipped: {od} -> {nd}", od, nd, priority=True)
        else:
            d.unchanged.append(f"{lab} direction ({nd})")

    # headline: total notified
    record(d, "total_notified_amount", f"{lab} total notified amount",
           _total(old_rows, "notified_amount"), _total(new_rows, "notified_amount"), "amount")

    for key, row in new_rows.items():
        if key not in old_rows:
            amt = to_num(row.get("notified_amount"))
            extra = f" (notified {fmt(amt)} Rs crore)" if amt is not None else ""
            add_change(d, "tenor_added", f"{lab}: new tenor/security on offer: {key}{extra}",
                       None, key, key=key, priority=True)
            continue
        record(d, "notified_amount", f"{lab} {key} notified amount",
               old_rows[key].get("notified_amount"), row.get("notified_amount"), "amount", key=key)

    for key in old_rows:
        if key not in new_rows:
            add_change(d, "tenor_missing",
                       f"{lab}: {key} was on offer in the previous announcement but is missing this time",
                       key, None, key=key, priority=True)
    return d


def compare_result(new: Release, prev: Release | None, announcement: Release | None) -> Diff:
    family, _ = split_item_id(new.item_id)
    lab = FAMILY_LABEL[family]
    d = Diff(new.item_id, new.release_date, prev.release_date if prev else None)
    new_rows = index_rows(new.rows, f"{new.item_id} (new)")
    old_rows = index_rows(prev.rows, f"{prev.item_id} (previous)") if prev else {}
    # Under-subscription is routine for VRR/VRRR, so it is never a priority flag there
    # (bid-cover and accepted-vs-notified still show as ordinary changes).
    strict = family not in ("vrr", "vrrr")
    ann_rows = index_rows(announcement.rows, f"{announcement.item_id}") if announcement else {}

    if prev is None:
        d.info.append(f"First recorded {lab} result; nothing to compare against.")

    for key, row in new_rows.items():
        # 1) versus the previous result of the same tenor
        if prev is not None:
            if key not in old_rows:
                d.info.append(f"{lab} {key}: no previous result for this tenor/security to compare against")
            else:
                p = old_rows[key]
                for fld, name, kind in CUTOFF_FIELDS:
                    record(d, fld, f"{lab} {key} {name}", p.get(fld), row.get(fld), kind, key=key)
                record(d, "bid_cover", f"{lab} {key} bid-cover", p.get("bid_cover"), row.get("bid_cover"),
                       "ratio", key=key)
                record(d, "accepted_amount", f"{lab} {key} amount accepted", p.get("accepted_amount"),
                       row.get("accepted_amount"), "amount", key=key)
                record(d, "notified_amount", f"{lab} {key} notified amount", p.get("notified_amount"),
                       row.get("notified_amount"), "amount", key=key)

        # 2) the result's own red flags
        bc = to_num(row.get("bid_cover"))
        if strict and bc is not None and bc < 1:
            add_change(d, "undersubscribed", f"{lab} {key}: bid-cover {fmt(bc)}x is below 1.0x (undersubscribed)",
                       None, bc, key=key, priority=True)
        dev = to_num(row.get("devolvement_amount"))
        if dev is not None and dev > EPS:
            add_change(d, "devolvement", f"{lab} {key}: devolvement of {fmt(dev)} Rs crore",
                       None, dev, key=key, priority=True)

        # 3) accepted versus the notified amount in its own announcement (else the result's own notified)
        arow = ann_rows.get(key)
        notified = to_num(arow.get("notified_amount")) if arow else to_num(row.get("notified_amount"))
        source = "announcement" if arow else "result"
        accepted = to_num(row.get("accepted_amount"))
        what = "accepted"
        if family in ("cg", "sg") and to_num(row.get("total_allotment_amount")) is not None:
            accepted, what = to_num(row.get("total_allotment_amount")), "total allotment"
        if family == "tbill":
            continue    # T-Bills: notified vs accepted is deliberately not judged (shown in the table instead)
        if announcement is not None and arow is None:
            d.info.append(f"{lab} {key}: not found in the matching announcement")
        if notified is not None and accepted is not None:
            gap = accepted - notified
            if abs(gap) < EPS:
                d.unchanged.append(f"{lab} {key} {what} = notified")
            else:
                pc = pct_change(notified, accepted)
                pc_txt = f", {signed(pc, 1)}%" if pc is not None else ""
                verdict = "below" if gap < 0 else "above"
                c = add_change(
                    d, "accepted_vs_notified",
                    f"{lab} {key}: {what} {fmt(accepted)} vs notified {fmt(notified)} Rs crore "
                    f"({signed(gap)}{pc_txt}) - {what} {verdict} notified ({source})",
                    notified, accepted, key=key, priority=strict and gap < 0, comparison="announcement")
                c.delta, c.unit, c.pct_change = round(gap, 2), "Rs crore", pc

    for key in old_rows:
        if key not in new_rows:
            d.info.append(f"{lab} {key}: present in the previous result but not in this one")
    for key in ann_rows:
        if key not in new_rows:
            d.info.append(f"{lab} {key}: notified in the announcement but has no row in this result")
    return d
