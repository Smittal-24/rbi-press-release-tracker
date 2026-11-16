"""MPC Minutes comparison (brief section 6).

Release shape: fields {repo_rate, decision, stance, inflation_projection, growth_projection,
inflation_outlook, growth_outlook}; rows = one per member {key: member name, vote: hold|cut|hike,
vote_bps, rationale}.
"""
from __future__ import annotations

from collections import Counter

from .models import Diff, Release
from .utils import add_change, index_rows, record, to_num


def _norm(s) -> str:
    return " ".join(str(s).split()).casefold() if s is not None else ""


def _text_change(d: Diff, metric: str, label: str, old, new, priority: bool = True) -> None:
    if not _norm(old) and not _norm(new):
        return
    if not _norm(old) or not _norm(new):
        d.info.append(f"{label}: not comparable (previous={old!r}, new={new!r})")
        return
    if _norm(old) == _norm(new):
        d.unchanged.append(label)
        return
    add_change(d, metric, f"{label} changed: '{old}' -> '{new}'", old, new, priority=priority)


def _split(rows: dict[str, dict]) -> str:
    counts = Counter(str(r.get("vote", "")).strip().lower() for r in rows.values())
    return ", ".join(f"{n} {v}" for v, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def compare_mpc(new: Release, prev: Release | None) -> Diff:
    d = Diff(new.item_id, new.release_date, prev.release_date if prev else None)
    if prev is None:
        d.info.append("First recorded MPC minutes; nothing to compare against.")
        return d
    nf, pf = new.fields, prev.fields

    # policy rate (priority whenever it moves)
    record(d, "repo_rate", "Policy repo rate", pf.get("repo_rate"), nf.get("repo_rate"), "yield", priority=True)
    _text_change(d, "decision", "Policy decision", pf.get("decision"), nf.get("decision"))
    _text_change(d, "stance", "Policy stance", pf.get("stance"), nf.get("stance"))

    # explicit outlook shifts
    record(d, "inflation_projection", "Inflation projection", pf.get("inflation_projection"),
           nf.get("inflation_projection"), "pp", priority=True)
    record(d, "growth_projection", "GDP growth projection", pf.get("growth_projection"),
           nf.get("growth_projection"), "pp", priority=True)
    _text_change(d, "inflation_outlook", "Inflation outlook language", pf.get("inflation_outlook"),
                 nf.get("inflation_outlook"))
    _text_change(d, "growth_outlook", "Growth outlook language", pf.get("growth_outlook"),
                 nf.get("growth_outlook"))

    # votes
    new_m = index_rows(new.rows, "mpc_minutes (new)")
    old_m = index_rows(prev.rows, "mpc_minutes (previous)")
    ns, os_ = _split(new_m), _split(old_m)
    if ns != os_:
        add_change(d, "vote_split", f"Vote split changed: {os_} -> {ns}", os_, ns)
    else:
        d.unchanged.append(f"vote split ({ns})")

    for name, row in new_m.items():
        if name not in old_m:
            d.info.append(f"{name}: not a member in the previous minutes")
            continue
        ov = str(old_m[name].get("vote", "")).strip().lower()
        nv = str(row.get("vote", "")).strip().lower()
        if ov != nv:
            add_change(d, "member_vote_switch", f"{name} switched vote: {ov} -> {nv}", ov, nv,
                       key=name, priority=True)
            continue
        ob, nb = to_num(old_m[name].get("vote_bps")), to_num(row.get("vote_bps"))
        if ob is not None and nb is not None and abs(ob - nb) > 1e-9:
            add_change(d, "member_vote_size", f"{name}: {nv} size changed {ob:g} bps -> {nb:g} bps",
                       ob, nb, key=name)
        else:
            d.unchanged.append(f"{name} ({nv})")
    for name in old_m:
        if name not in new_m:
            d.info.append(f"{name}: member in the previous minutes but not in this one")
    return d
