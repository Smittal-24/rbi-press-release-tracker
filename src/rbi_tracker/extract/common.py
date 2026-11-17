"""Shared helpers for turning RBI release pages into structured data (rule-based extraction).

Everything here is pure: HTML in, plain Python out. Nothing is estimated: a value that is not
published (shown as "-", "NA" or blank) becomes None. "NIL" is a published zero.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag


class ExtractionError(Exception):
    """The page does not have the structure the extractor expects."""


def clean(s) -> str:
    return " ".join(str(s).split())


def num(s) -> float | None:
    """Parse a published number. '-', 'NA', blank -> None; 'NIL' -> 0.0; 'N,NNN.NN' -> float."""
    if s is None:
        return None
    t = clean(s).replace("\u20b9", "").replace(",", "").replace("%", "").strip()
    if t.lower() == "nil":
        return 0.0
    if t.lower() in ("", "-", "\u2013", "na", "n.a.", "n.a"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def first_number(s) -> float | None:
    """First number inside a string such as ': Rs 25,000 crore'."""
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", clean(s))
    return float(m.group(0).replace(",", "")) if m else None


def parse_date(text: str) -> date | None:
    """'November 20, 2026 (Friday)', 'Sep 07, 2031', 'Nov. 6, 2026' -> date."""
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", clean(text))
    if not m:
        return None
    mon, day, year = m.groups()
    for f in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(f"{mon} {day} {year}", f).date()
        except ValueError:
            continue
    return None


def load(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def body_node(soup: BeautifulSoup) -> Tag:
    """The press release body (the `table.td` wrapper); falls back to the whole page."""
    return soup.select_one("table.td") or soup


def leaf_tables(node: Tag) -> list[Tag]:
    """Innermost tables inside `node`, in page order (the data tables)."""
    return [t for t in node.find_all("table") if not t.find("table")]


def grid(table: Tag) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [clean(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"], recursive=False)]
        if any(cells):
            rows.append(cells)
    return rows


def body_text(soup: BeautifulSoup) -> str:
    return clean(body_node(soup).get_text(" ", strip=True))


def release_meta(soup: BeautifulSoup) -> tuple[str | None, str]:
    """(release date ISO, 'Press Release: YYYY-YYYY/NNNN' reference) read from the page."""
    full = clean(soup.get_text(" ", strip=True))
    m = re.search(r"Date\s*:\s*([A-Za-z]{3,9}\.? \d{1,2}, \d{4})", full)
    d = parse_date(m.group(1)) if m else None
    ref = re.search(r"Press Release:\s*(\d{4}-\d{4}/\d+)", full)
    return (d.isoformat() if d else None), (f"Press Release: {ref.group(1)}" if ref else "")


# ------------------------------------------------------------------ column-style result tables
_ROMAN = re.compile(r"^[IVX]+\.$")
_SUB = re.compile(r"^\((?:i{1,3}|iv)\)\s*(.*)$", re.I)
_ANNOT = re.compile(r"^\((?:YTM|WAY)\b|^\(\d+\s+bids?\)", re.I)
_HEADER_FIRST = {"", "auction results", "item", "security", "tenor"}


def norm_label(s: str) -> str:
    s = re.sub(r"^[IVX]+\.\s*", "", clean(s))
    s = re.sub(r"\s+-\s+", "-", s).rstrip(":").strip().lower()
    return s


def _norm_sub(s: str) -> str:
    m = _SUB.match(clean(s))
    t = (m.group(1) if m else s).strip().lower().rstrip(".")
    return {"no": "number"}.get(t, t)


def read_columns(tables: list[Tag]) -> tuple[list[str], dict[str, list[str]]]:
    """Read result tables laid out as one value column per security / tenor.

    Returns (column names, metrics) where metrics maps a normalised label such as
    'competitive bids received/amount' to one raw string per column. Annotation rows such as
    '(YTM: 7.32%)' are stored under '<label>|note'. Tables that continue the same layout with more
    columns (as the SG result does) are joined side by side.
    """
    columns: list[str] = []
    metrics: dict[str, list[str]] = {}

    def pad(vals: list[str], n: int) -> list[str]:
        return (vals + [""] * n)[:n]

    for table in tables:
        rows = grid(table)
        header_i = next((i for i, r in enumerate(rows)
                         if len(r) >= 2 and r[0].lower() in _HEADER_FIRST and any(r[1:])), None)
        if header_i is None:
            continue
        cols = rows[header_i][1:]
        n_before, n = len(columns), len(cols)
        local: dict[str, list[str]] = {}
        section, last_key = "", None
        for r in rows[header_i + 1:]:
            if len(r) == 1 and not _ANNOT.match(r[0]):
                continue                                        # footnotes / captions
            if _ANNOT.match(r[0]):
                if last_key:
                    local[last_key + "|note"] = pad(r, n)
                continue
            if _ROMAN.match(r[0]) and len(r) >= 2:
                label, vals = norm_label(r[1]), r[2:]
                section = label
            elif _SUB.match(r[0]):
                label, vals = f"{section}/{_norm_sub(r[0])}", r[1:]
            else:
                label, vals = norm_label(r[0]), r[1:]
                section = label
            if any(v for v in vals):
                local[label] = pad(vals, n)
                last_key = label
        for key in set(metrics) | set(local):
            metrics[key] = pad(metrics.get(key, []), n_before) + local.get(key, [""] * n)
        columns += cols
    if not columns:
        raise ExtractionError("no result columns found")
    return columns, metrics


def metric(metrics: dict[str, list[str]], pattern: str, i: int, note: bool = False) -> str:
    """Raw string of the first metric whose label matches `pattern`, for column i ('' if absent)."""
    rx = re.compile(pattern, re.I)
    for key, vals in metrics.items():
        if key.endswith("|note") != note:
            continue
        if rx.search(key[:-5] if note else key):
            return vals[i] if i < len(vals) else ""
    return ""


def note_number(raw: str, tag: str) -> float | None:
    """'(YTM: 7.3203%)' -> 7.3203 for tag 'YTM'."""
    m = re.search(rf"{tag}:\s*(-?[\d.]+)", raw or "", re.I)
    return float(m.group(1)) if m else None