"""Fetch one press release's detail page (the page behind a `prid`)."""
from __future__ import annotations

import time

import requests
from bs4 import BeautifulSoup

from .listing import CANONICAL_DETAIL, HEADERS, FetchError


def fetch_detail_html(prid: str, session: requests.Session | None = None, retries: int = 3,
                      timeout: int = 30, backoff: float = 2.0) -> str:
    """Raw HTML of a press release detail page. Retries transient errors; a block fails fast."""
    url = CANONICAL_DETAIL.format(prid=prid)
    session = session or requests.Session()
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=timeout)
        except requests.RequestException as e:
            last = FetchError(f"network error fetching prid {prid}: {e}")
        else:
            if r.status_code == 200:
                return r.text
            last = FetchError(f"HTTP {r.status_code} fetching prid {prid}", status=r.status_code)
            if r.status_code in (401, 403, 404):
                break
        if attempt < retries - 1:
            time.sleep(backoff * (attempt + 1))
    raise last  # type: ignore[misc]


def clean_html(html: str) -> str:
    """Strip scripts, styles, head and hidden form state: keeps the visible content tables only.

    Used to store small, readable copies of real releases as test fixtures.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "noscript", "head", "link", "meta", "iframe"]):
        tag.decompose()
    for tag in soup.find_all("input", attrs={"type": "hidden"}):
        tag.decompose()
    for tag in soup.find_all(True):          # drop inline event handlers / styling noise
        for attr in [a for a in tag.attrs if a.startswith("on") or a == "style"]:
            del tag.attrs[attr]
    return soup.prettify()


def page_headline(html: str) -> str:
    """Best-effort one-line description of a detail page (first text of the first content table)."""
    soup = BeautifulSoup(html, "lxml")
    t = soup.select_one("table.tablebg")
    return " ".join(t.get_text(" ", strip=True).split())[:110] if t else "(no table.tablebg found)"
