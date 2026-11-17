"""Small pure helpers shared by the engine modules."""
from __future__ import annotations

from typing import Any

from .models import Change, Diff

EPS = 1e-9


def to_num(x: Any) -> float | None:
    """Numeric value of x, or None for blank / non-numeric / bool."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().replace(",", "").rstrip("%").strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def pretty(name: str) -> str:
    if name.startswith("ytd_"):
        return pretty(name[4:]) + " (year to date)"
    return name.replace("_", " ")


def fmt(x: float, nd: int = 2) -> str:
    s = f"{x:,.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def signed(x: float, nd: int = 2) -> str:
    s = f"{x:+,.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def fmt_rate(x: float) -> str:
    """Percent value with at least 2 decimals (6.5 -> 6.50, 6.5234 -> 6.5234)."""
    head, _, tail = f"{x:.4f}".rstrip("0").partition(".")
    return f"{head}.{tail.ljust(2, '0')}"


def pct_change(prev: float, new: float) -> float | None:
    """% change; denominator is abs(prev) so a move from a negative base has a sensible sign."""
    if abs(prev) < EPS:
        return None
    return round((new - prev) / abs(prev) * 100, 2)


def index_rows(rows: list[dict[str, Any]], what: str) -> dict[str, dict[str, Any]]:
    """Index rows by their unique string 'key'. Duplicates are an extraction bug -> fail loudly."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = r.get("key")
        if k is None or str(k).strip() == "":
            raise ValueError(f"{what}: row without a 'key': {r}")
        k = str(k)
        if k in out:
            raise ValueError(f"{what}: duplicate row key {k!r}; the extractor must make keys unique")
        out[k] = r
    return out


def add_change(
    d: Diff,
    metric: str,
    note: str,
    previous: Any = None,
    new: Any = None,
    key: str | None = None,
    priority: bool = False,
    comparison: str = "previous",
) -> Change:
    c = Change(metric=metric, note=note, previous=previous, new=new, key=key,
               priority=priority, comparison=comparison)
    d.changes.append(c)
    return c


def record(
    d: Diff,
    metric: str,
    label: str,
    prev: Any,
    new: Any,
    kind: str,
    key: str | None = None,
    comparison: str = "previous",
    priority: bool = False,
) -> Change | None:
    """Compare two numeric values and record the result on the diff.

    kind: "yield" (values in %, delta in bps) | "pp" (values in %, delta in percentage points) |
          "price" (absolute Rs delta) | "ratio" (x) | "amount" (Rs crore) | "level" (generic number)
    Returns the Change if the value moved; otherwise logs it as unchanged (or as not comparable
    when only one side is present) and returns None.
    """
    p, n = to_num(prev), to_num(new)
    if p is None and n is None:
        return None
    if p is None or n is None:
        d.info.append(f"{label}: not comparable (previous={prev!r}, new={new!r})")
        return None
    if abs(n - p) < EPS:
        d.unchanged.append(label)
        return None

    pc = pct_change(p, n)
    pc_txt = f", {signed(pc, 1)}%" if pc is not None else ""
    if kind == "yield":
        delta, unit = round((n - p) * 100, 2), "bps"
        note = f"{label}: {fmt_rate(p)}% -> {fmt_rate(n)}% ({signed(delta, 1)} bps)"
    elif kind == "pp":
        delta, unit = round(n - p, 2), "pp"
        note = f"{label}: {fmt_rate(p)}% -> {fmt_rate(n)}% ({signed(delta)} pp)"
    elif kind == "price":
        delta, unit = round(n - p, 4), "Rs"
        note = f"{label}: {fmt(p, 4)} -> {fmt(n, 4)} ({signed(delta, 4)})"
    elif kind == "ratio":
        delta, unit = round(n - p, 2), "x"
        note = f"{label}: {fmt(p)}x -> {fmt(n)}x ({signed(delta)}x)"
    elif kind == "amount":
        delta, unit = round(n - p, 2), "Rs crore"
        note = f"{label}: {fmt(p)} -> {fmt(n)} Rs crore ({signed(delta)}{pc_txt})"
    else:  # level
        delta, unit = round(n - p, 4), ""
        note = f"{label}: {fmt(p)} -> {fmt(n)} ({signed(delta)}{pc_txt})"

    c = Change(metric=metric, note=note, previous=p, new=n, key=key, delta=delta, unit=unit,
               pct_change=pc, comparison=comparison, priority=priority)
    d.changes.append(c)
    return c
