"""Google Chat: message text and the webhook poster.

One message per release (never bundled). The webhook URL is a secret: it is read from the
GCHAT_WEBHOOK_URL environment variable, never stored in the repo, and never printed or logged.
"""
from __future__ import annotations

import os
from datetime import date

import requests

from ..engine.models import Diff, Release
from ..engine.utils import fmt
from . import summaries

MAX_CHARS = 3800            # Google Chat text messages are limited to 4,096 characters


class PostError(Exception):
    """The message could not be delivered (the message never contains the webhook URL)."""


class GChatPoster:
    def __init__(self, url: str | None = None, timeout: int = 20):
        self._url = url or os.environ.get("GCHAT_WEBHOOK_URL", "")
        self.timeout = timeout
        if not self._url:
            raise PostError("GCHAT_WEBHOOK_URL is not set")

    def post(self, text: str) -> None:
        try:
            r = requests.post(self._url, json={"text": text}, timeout=self.timeout)
        except requests.RequestException as e:
            raise PostError(f"network error posting to Google Chat ({type(e).__name__})") from None
        if r.status_code >= 300:
            raise PostError(f"Google Chat rejected the message (HTTP {r.status_code})")


class PrintPoster:
    """Dry run: shows what would be posted."""

    def post(self, text: str) -> None:
        print("-" * 70)
        print(text)


def _nice_date(iso: str | None) -> str:
    if not iso:
        return "-"
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b %Y')}"


def _clip(lines: list[str]) -> str:
    out, used = [], 0
    for i, line in enumerate(lines):
        if used + len(line) + 1 > MAX_CHARS:
            out.append(f"... and {len(lines) - i} more line(s) not shown")
            break
        out.append(line)
        used += len(line) + 1
    return "\n".join(out)


def _cell(x, nd: int = 3, fixed: bool = False) -> str:
    if x is None:
        return "-"
    return f"{float(x):.{nd}f}" if fixed else fmt(float(x), nd)


def tbill_table(release: Release, previous: Release | None) -> list[str]:
    """RBI's cut-off result figures as an aligned monospace table, one column per tenor, plus a row with
    the change in cut-off yield (bps) against the previous T-Bill auction of the same tenor."""
    rows = release.rows
    prev = {r["key"]: r for r in previous.rows} if previous else {}

    def yield_change(r):
        a, b = r.get("cutoff_yield"), prev.get(r["key"], {}).get("cutoff_yield")
        return None if a is None or b is None else (float(a) - float(b)) * 100

    spec = [
        ("Notified", lambda r: _cell(r.get("notified_amount"))),
        ("Comp. bids received", lambda r: _cell(r.get("bids_received_amount"))),
        ("Comp. bids accepted", lambda r: _cell(r.get("accepted_amount"))),
        ("Non-comp. accepted", lambda r: _cell(r.get("noncomp_accepted_amount"))),
        ("Cut-off price (Rs)", lambda r: _cell(r.get("cutoff_price"), 4, fixed=True)),
        ("Cut-off yield (%)", lambda r: _cell(r.get("cutoff_yield"), 4, fixed=True)),
        ("Wtd avg yield (%)", lambda r: _cell(r.get("wtd_avg_yield"), 4, fixed=True)),
        ("Yield chg vs prev (bps)", lambda r: "n/a" if yield_change(r) is None else f"{yield_change(r):+.1f}"),
    ]
    names = [str(r.get("security") or r["key"]) for r in rows]
    cells = [[fn(r) for r in rows] for _, fn in spec]
    w0 = max(len(lab) for lab, _ in spec)
    widths = [max(len(names[i]), *(len(c[i]) for c in cells)) for i in range(len(rows))]
    out = ["Amount in Rs crore", "```", " " * w0 + "  " + "  ".join(n.rjust(widths[i]) for i, n in enumerate(names))]
    for (lab, _), c in zip(spec, cells):
        out.append(lab.ljust(w0) + "  " + "  ".join(c[i].rjust(widths[i]) for i in range(len(rows))))
    out.append("```")
    out.append(f"Yield change is against the previous T-Bill auction ({_nice_date(previous.release_date)})."
               if previous else "Yield change: n/a - first recorded T-Bill result, nothing to compare against yet.")
    return out


def format_release(label: str, release: Release, diff: Diff, url: str, previous: Release | None = None) -> str:
    head = [f"*RBI | {label}* - {_nice_date(release.release_date)}"]
    if release.reference:
        head.append(release.reference)
    head.append(url)
    if release.item_id == "tbill_result":
        flags = ["PRIORITY: " + c.note for c in diff.priority_changes]
        body = tbill_table(release, previous) + flags
    elif release.item_id == "bop":
        body = summaries.bop_summary(release, previous, diff)
    elif release.item_id == "sectoral_credit":
        body = summaries.credit_summary(release, previous)
    else:
        if diff.has_previous:
            head.append(f"Compared with the previous release ({_nice_date(diff.previous_date)}):")
        body = ["- " + ln for ln in diff.summary_lines()] or ["- No changes detected."]
    review = release.fields.get("needs_review") or []
    tail = [f"WARNING - needs a human check: {r}" for r in review]
    return _clip(head + body + tail)


def format_extraction_warning(label: str, title: str, url: str, error: str, attempt: int, max_attempts: int) -> str:
    more = "Will retry on the next run." if attempt < max_attempts else "Giving up after repeated failures."
    return _clip([f"*RBI tracker WARNING* - could not read a new release automatically",
                  f"{label}: {title}", url, f"Reason: {error}", more])


def format_listing_warning(error: str) -> str:
    return _clip(["*RBI tracker WARNING* - could not load the RBI press release page", f"Reason: {error}",
                  "Nothing was processed; the next run will try again."])


def format_quiet(today_iso: str) -> str:
    return f"RBI tracker: no new tracked releases on {_nice_date(today_iso)}."