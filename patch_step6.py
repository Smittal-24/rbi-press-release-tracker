"""Step 6 patch: T-Bills not judged on notified vs accepted; job passes the previous release to the message.
Safe to run twice."""
import pathlib


def sub(path, old, new):
    p = pathlib.Path(path)
    t = p.read_text(encoding="utf-8")
    if new in t:
        print("already applied:", path)
        return
    assert old in t, f"expected text not found in {path}: {old[:60]!r}"
    p.write_text(t.replace(old, new, 1), encoding="utf-8", newline="\n")
    print("patched:", path)


sub("src/rbi_tracker/engine/auction.py",
    """        # T-Bill notified amounts cover competitive + non-competitive allotment, so judge the total
        if family == "tbill" and to_num(row.get("total_allotment_amount")) is not None:
            accepted = to_num(row.get("total_allotment_amount"))
""",
    """        if family == "tbill":
            continue    # T-Bills: notified vs accepted is deliberately not judged (shown in the table instead)
""")

sub("src/rbi_tracker/job.py",
    """        diff = compare(release, archive.previous(item_id, release.release_date, prid),
                       archive.matching_announcement(item_id, release.release_date, prid))
        if send(gchat.format_release(label, release, diff, rec["detail_url"])):""",
    """        previous = archive.previous(item_id, release.release_date, prid)
        diff = compare(release, previous, archive.matching_announcement(item_id, release.release_date, prid))
        if send(gchat.format_release(label, release, diff, rec["detail_url"], previous)):""")

sub("tests/test_engine_auctions.py",
    """    ann = rel("tbill_announcement", "2026-11-10", rows=[{"key": "91D", "notified_amount": 8000}])
    res = rel("tbill_result", "2026-11-11", rows=[{"key": "91D", "accepted_amount": 8500, "bid_cover": 3.0}])
    c = find(compare(res, None, announcement=ann), "accepted_vs_notified", "91D")[0]""",
    """    ann = rel("cg_announcement", "2026-11-10", rows=[{"key": "10Y", "notified_amount": 8000}])
    res = rel("cg_result", "2026-11-11", rows=[{"key": "10Y", "accepted_amount": 8500, "bid_cover": 3.0}])
    c = find(compare(res, None, announcement=ann), "accepted_vs_notified", "10Y")[0]""")