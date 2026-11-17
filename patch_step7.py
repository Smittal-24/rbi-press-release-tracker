"""Step 7 patch: CG and SG results judge TOTAL allotment (competitive + non-competitive) against notified.
Safe to run twice."""
import pathlib


def sub(path, old, new):
    p = pathlib.Path(path)
    t = p.read_text(encoding="utf-8")
    if new in t:
        print("already applied:", path, "|", new.strip().splitlines()[0][:60])
        return
    assert old in t, f"expected text not found in {path}: {old[:60]!r}"
    p.write_text(t.replace(old, new, 1), encoding="utf-8", newline="\n")
    print("patched:", path)


P = "src/rbi_tracker/engine/auction.py"
sub(P,
    '''        accepted = to_num(row.get("accepted_amount"))
        if family == "tbill":''',
    '''        accepted = to_num(row.get("accepted_amount"))
        what = "accepted"
        if family in ("cg", "sg") and to_num(row.get("total_allotment_amount")) is not None:
            accepted, what = to_num(row.get("total_allotment_amount")), "total allotment"
        if family == "tbill":''')
sub(P, '''d.unchanged.append(f"{lab} {key} accepted = notified")''',
       '''d.unchanged.append(f"{lab} {key} {what} = notified")''')
sub(P, '''f"{lab} {key}: accepted {fmt(accepted)} vs notified {fmt(notified)} Rs crore "
                    f"({signed(gap)}{pc_txt}) - accepted {verdict} notified ({source})",''',
       '''f"{lab} {key}: {what} {fmt(accepted)} vs notified {fmt(notified)} Rs crore "
                    f"({signed(gap)}{pc_txt}) - {what} {verdict} notified ({source})",''')