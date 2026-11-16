"""Fetch and parse the RBI Press Releases listing page.

Page structure (checked Nov 2026): one `table.tablebg`. A date header row
(`td.tableheader > h2 > b`, e.g. "Nov 16, 2026") is followed by that day's item rows. Each item row
has a title link (`a.link2`, href contains `prid=NNNNN`) and a PDF link.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..paths import load_settings

CANONICAL_DETAIL = "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid={prid}"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-IN,en;q=0.9",
}


class FetchError(Exception):
    """Page unreachable / blocked (carries the HTTP status where there is one)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class ParseError(Exception):
    """The page was fetched but no longer looks like we expect (RBI changed its layout)."""


@dataclass
class PressReleaseEntry:
    prid: str               # RBI's press release id: stable unique key
    release_date: str       # ISO date from the listing's date header
    title: str
    detail_url: str
    pdf_url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_date(text: str) -> date | None:
    text = " ".join(text.split())
    for f in ("%b %d, %Y", "%B %d, %Y", "%b. %d, %Y"):
        try:
            return datetime.strptime(text, f).date()
        except ValueError:
            continue
    return None


def parse_listing(html: str, base_url: str | None = None) -> list[PressReleaseEntry]:
    """Parse the listing HTML into entries, in page order (newest first)."""
    base_url = base_url or load_settings()["sources"]["press_releases_url"]
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.tablebg")
    if table is None:
        raise ParseError("press release table (table.tablebg) not found: RBI may have changed the page")

    entries: list[PressReleaseEntry] = []
    current: date | None = None
    for tr in table.find_all("tr"):
        header = tr.select_one("td.tableheader")
        if header is not None:
            d = _parse_date(header.get_text(" ", strip=True))
            if d:
                current = d
            continue
        a = tr.select_one('a[href*="prid="]')
        if a is None:
            continue
        if current is None:
            raise ParseError("press release row found before any date header")
        prid = re.search(r"prid=(\d+)", a["href"], re.I).group(1)
        pdf = next((x for x in tr.find_all("a", href=True)
                    if x is not a and x["href"].split("?")[0].lower().endswith(".pdf")), None)
        entries.append(PressReleaseEntry(
            prid=prid,
            release_date=current.isoformat(),
            title=" ".join(a.get_text(" ", strip=True).split()),
            detail_url=CANONICAL_DETAIL.format(prid=prid),
            pdf_url=urljoin(base_url, pdf["href"]) if pdf else None,
        ))
    if not entries:
        raise ParseError("no press releases found in the table")
    return entries


def fetch_listing(url: str | None = None, session: requests.Session | None = None,
                  retries: int = 3, timeout: int = 30, backoff: float = 2.0) -> list[PressReleaseEntry]:
    """Download and parse the listing. Retries transient failures; a block (403) fails clearly."""
    url = url or load_settings()["sources"]["press_releases_url"]
    session = session or requests.Session()
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=timeout)
        except requests.RequestException as e:
            last = FetchError(f"network error fetching {url}: {e}")
        else:
            if r.status_code == 200:
                return parse_listing(r.text, url)
            last = FetchError(f"HTTP {r.status_code} fetching {url}", status=r.status_code)
            if r.status_code in (401, 403, 404):    # retrying will not help
                break
        if attempt < retries - 1:
            time.sleep(backoff * (attempt + 1))
    raise last  # type: ignore[misc]
