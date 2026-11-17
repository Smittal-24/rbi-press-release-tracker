"""Tenor buckets: the key that lets results be compared with the previous result of the same tenor.

Rule (confirmed): residual maturity from the auction date, rounded to the nearest whole year.
6.53% GS 2031 repaying Sep 07, 2031 auctioned Nov 20, 2026 -> 4.8 years -> "5Y".
If only the maturity YEAR is known (CG result pages), the exact date is looked up from the matching
announcement when available; otherwise the year difference is used and the row is marked approximate.
"""
from __future__ import annotations

import math
import re
from datetime import date


def bucket_from_years(years: float) -> str:
    return f"{int(math.floor(years + 0.5))}Y"


def maturity_year(security: str) -> int | None:
    years = re.findall(r"\b(20\d{2})\b", security)
    return int(years[-1]) if years else None


def tenor_bucket(security: str, ref_date: date, maturity: date | None = None) -> tuple[str, bool]:
    """Return (bucket like '10Y', approximate?). approximate=True when only the year was known."""
    if maturity is not None:
        return bucket_from_years((maturity - ref_date).days / 365.25), False
    y = maturity_year(security)
    if y is None:
        raise ValueError(f"cannot work out a maturity year from {security!r}")
    return bucket_from_years(y - ref_date.year), True


def unique_keys(keys: list[str]) -> list[str]:
    """Make row keys unique: a second '7Y' becomes '7Y #2' (so the engine never sees duplicates)."""
    seen: dict[str, int] = {}
    out = []
    for k in keys:
        seen[k] = seen.get(k, 0) + 1
        out.append(k if seen[k] == 1 else f"{k} #{seen[k]}")
    return out